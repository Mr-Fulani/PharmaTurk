"""Детерминированные тексты не медицинских товаров: LLM только как fallback."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.rules import vocab
from apps.ai.services.rules.facts import ProductFacts, _brand_from_description, clean_source_text, collect_facts, parse_name
from apps.ai.services.rules.pipeline import _dynamic_attributes, plan_rule_content
from apps.ai.services.rules.text import build_fact_description, build_seo, build_titles, is_thin_source
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import extract_sizes_from_input, size_inventory_block_reason
from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    MedicineProduct,
    Product,
    ShoeProduct,
    ShoeVariant,
    ShoeVariantSize,
)


def _facts(name, product_type="shoes", **extra):
    facts = ProductFacts(product_type=product_type, **extra)
    parse_name(name, facts)
    return facts


def _llm_result(content):
    return {
        "content": content,
        "tokens": {"prompt": 400, "completion": 300, "total": 700, "cached": 0},
        "cost_usd": 0.00024,
        "processing_time_ms": 5,
    }


def _generator(llm):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator.llm = llm
    return generator


# --- словари ---


@pytest.mark.parametrize(
    "raw, gender, ru, en",
    [
        ("Beyaz", vocab.F, "белая", "White"),
        ("Si̇yah", vocab.PL, "черные", "Black"),
        ("Açık İndigo / S61986Z8 + 13 Renk Beden Seç", vocab.M, "цвета индиго", "Indigo"),
        ("Koyu Mavi", vocab.N, "темно-синее", "Dark blue"),
        ("Yeni Siyah", vocab.M, "черный", "Black"),
        ("Haki", vocab.F, "цвета хаки", "Khaki"),
    ],
)
def test_colors_translate_with_russian_agreement(raw, gender, ru, en):
    color = vocab.translate_color(raw)
    if raw.startswith("Açık İndigo"):
        assert color is None  # модификатор у несклоняемого цвета не собираем
        return
    assert color.ru_for(gender) == ru
    assert color.en == en


def test_compound_and_unknown_colors_are_not_guessed():
    assert vocab.translate_color("Siyah-Kahverengi") is None
    assert vocab.translate_color("Orta İndigo Rodeo") is not None
    assert vocab.translate_color("Turuncu-Fuşya") is None


def test_composition_shoe_materials_and_furniture_finish():
    assert vocab.translate_composition("%100 PAMUK") == ("100% хлопок", "100% cotton")
    assert vocab.translate_composition("%95 Pamuk %5 Elastan") == (
        "95% хлопок, 5% эластан",
        "95% cotton, 5% elastane",
    )
    assert vocab.translate_composition("%100 Unobtainium") is None
    assert vocab.translate_shoe_material("TEKSTIL/PU") == ("текстиль, полиуретан", "textile, polyurethane")
    assert vocab.translate_shoe_material("DERI (SIGIR)/TEKSTIL")[0] == "натуральная кожа (говяжья), текстиль"
    assert vocab.translate_furniture_finish("beyaz-aynalı cam") == ("белый/зеркальное стекло", "white/mirror glass")
    assert vocab.translate_furniture_finish("Axvall kırık beyaz") == ("Axvall молочный", "Axvall off-white")
    assert vocab.translate_furniture_finish("bilinmeyen renk") is None


# --- названия ---


@pytest.mark.parametrize(
    "name, product_type, ru, en",
    [
        ("BUCKY 6FX Beyaz Erkek Sneaker", "shoes", "Мужские кроссовки BUCKY 6FX, белые", "BUCKY 6FX Men's Sneakers, White"),
        (
            "Emr 1830 Hakiki Deri Erkek Ortopedik Sandalet Ayakkabı",
            "shoes",
            "Мужские сандалии Emr 1830 из натуральной кожи с ортопедической стелькой",
            "Emr 1830 Men's Genuine Leather Orthopedic Sandals",
        ),
        ("AIR MAX BIA (GS) Siyah Unisex Sneaker", "shoes", "Кроссовки унисекс AIR MAX BIA (GS), черные", "AIR MAX BIA (GS) Unisex Sneakers, Black"),
        (
            "Bisiklet Yaka Kısa Kollu Baskılı Erkek Tişört",
            "clothing",
            "Мужская футболка с круглым вырезом с коротким рукавом",
            "Men's Crew Neck Short Sleeve T-Shirt",
        ),
        (
            "BOGOSS VIBRANT LEATHER & SUMMER EDP 2X100ML ( 3.4 FL.OZ )",
            "perfumery",
            "Парфюмерная вода BOGOSS VIBRANT LEATHER & SUMMER, 2 × 100 мл",
            "BOGOSS VIBRANT LEATHER & SUMMER Eau de Parfum, 2 × 100 ml",
        ),
    ],
)
def test_titles_from_turkish_names(name, product_type, ru, en):
    titles = build_titles(_facts(name, product_type))
    assert titles == {"ru": ru, "en": en}


def test_unknown_turkish_word_falls_back_to_llm_title():
    facts = _facts("Erkek Hafif Günlük Deniz Ayakkabısı - Ortopedik Tabanlı Plaj ve Havuz Terliği")
    assert facts.untranslated == ["Plaj", "Havuz"]
    assert build_titles(facts) == {"ru": "", "en": ""}


def test_perfume_without_brand_or_model_needs_llm_title():
    facts = _facts("Parfüm Seti - Markalar - 850,00 TL", "perfumery")
    assert facts.kind.ru == "парфюмерный набор"
    assert build_titles(facts) == {"ru": "", "en": ""}


def test_brand_from_description_and_retailer_noise():
    product = SimpleNamespace(product_type="accessories", category=SimpleNamespace(slug="belts"), domain_item=None)
    facts = collect_facts(
        product,
        {
            "name": "Kemer - LC WAIKIKI - 199,99 TL",
            "brand": "LC Waikiki",
            "attributes": {"color": "Siyah", "gender": "men", "material": "Искусственная кожа"},
        },
    )
    assert build_titles(facts) == {
        "ru": "Мужской ремень LC Waikiki из искусственной кожи, черный",
        "en": "LC Waikiki Men's Faux Leather Belt, Black",
    }

    tshirt = SimpleNamespace(product_type="clothing", category=SimpleNamespace(slug="t-shirts"), domain_item=None)
    facts = collect_facts(
        tshirt,
        {"name": "Erkek Tişört", "brand": "Другое", "description": "U.S. Polo Assn. Erkek Tişört", "attributes": {"gender": "men"}},
    )
    assert facts.brand == "U.S. Polo Assn."
    assert build_titles(facts)["ru"] == "Мужская футболка U.S. Polo Assn."


def test_furniture_title_uses_type_series_and_finish():
    product = SimpleNamespace(product_type="furniture", category=SimpleNamespace(slug="dressers"), domain_item=None)
    facts = collect_facts(
        product,
        {"name": "MALM", "brand": "IKEA", "attributes": {"furniture_type": "6 çekmeceli şifonyer", "color": "beyaz-meşe görünümlü"}},
    )
    assert build_titles(facts) == {
        "ru": "Комод с 6 ящиками IKEA MALM, белый/под дуб",
        "en": "IKEA MALM Chest of 6 Drawers, white/oak effect",
    }


# --- описания и SEO ---


def test_thin_source_gets_fact_description_without_llm():
    facts = _facts("Routine Erkek Tişört", "clothing")
    facts.composition = vocab.translate_composition("%100 PAMUK")
    titles = build_titles(facts)
    assert is_thin_source("%100 PAMUK", "Routine Erkek Tişört", facts)
    description = build_fact_description(facts, titles)
    assert description["ru"].startswith("Мужская футболка Routine. Состав: 100% хлопок.")
    assert description["en"].startswith("Routine Men's T-Shirt. Composition: 100% cotton.")

    rich = (
        "%100 organik pamuk kumaştan üretilen Mercury Vortex tişört, rahat kesimiyle gün boyu "
        "konfor sunar. Bisiklet yaka tasarımı ve yumuşak dokulu baskı detayıyla sade bir görünüm."
    )
    assert not is_thin_source(rich, "Mercury Vortex Erkek Tişört", _facts("Mercury Vortex Erkek Tişört", "clothing"))


def test_seo_fits_limits_and_uses_site_wording():
    facts = _facts("BUCKY 6FX Beyaz Erkek Sneaker")
    titles = build_titles(facts)
    seo = build_seo(facts, titles, {"ru": "Легкие кроссовки из ПВХ. Второе предложение.", "en": "Light PVC sneakers. More."})
    assert seo["ru"]["seo_title"] == "Мужские кроссовки BUCKY 6FX, белые — купить с доставкой из Турции"
    # Название в именительном падеже: «Заказать мужская футболка» было ошибкой.
    assert seo["ru"]["seo_description"] == (
        "Мужские кроссовки BUCKY 6FX, белые. Оригинальный товар из Турции с доставкой. Легкие кроссовки из ПВХ."
    )
    assert seo["en"]["seo_title"].endswith("— buy with delivery from Turkey")
    assert "кроссовки BUCKY 6FX" in seo["ru"]["keywords"]
    long_title = {"ru": "Очень " * 20 + "длинное название", "en": ""}
    long_seo = build_seo(facts, long_title, {})
    assert len(long_seo["ru"]["seo_title"]) <= 70 and long_seo["ru"]["seo_title"].endswith("…")
    assert "en" not in long_seo


def test_lcw_source_header_and_legal_tail_are_removed():
    text = clean_source_text(
        "Ürün Kodu: 95674-08200-32 - 26865  - Renksiz - S000110517 NIVEA MEN Erkek Roll-on 50ml "
        "Ürün İçeriği ve Özellikleri Cinsiyet: Erkek İmalatçı / İthalatçı / Yetkili Temsilci: X A.Ş."
    )
    assert text == "NIVEA MEN Erkek Roll-on 50ml Cinsiyet: Erkek"
    assert clean_source_text("&lt;p&gt;Loft Erkek Tiş&amp;ouml;rt&lt;/p&gt;") == "Loft Erkek Tişört"


# --- пайплайн и БД ---


def _shoe(slug, description, **attrs):
    root = Category.objects.get_or_create(slug="rule-shoes", defaults={"name": "Обувь"})[0]
    category = Category.objects.get_or_create(slug="sneakers", defaults={"name": "Кроссовки", "parent": root})[0]
    brand = Brand.objects.get_or_create(name="Другое", defaults={"slug": "drugoe-rule"})[0]
    shoe = ShoeProduct.objects.create(
        name="BUCKY 6FX Beyaz Erkek Sneaker",
        slug=slug,
        description=description,
        category=category,
        brand=brand,
    )
    shoe.refresh_from_db()
    product = shoe.base_product
    product.external_data = {"attributes": {"color": "Beyaz", "gender": "men", "material": "Suni Deri", "sole_material": "KAUCUK", **attrs}}
    product.save()
    product.refresh_from_db()
    return product


RICH_SOURCE = (
    "Casual stilinize uyum sağlayan bu klasik sneaker, PVC materyali ile dayanıklılık ve hafiflik sunar. "
    "Beyaz rengi sayesinde her kıyafetle kombinlenebilir ve gün boyu konfor sağlar."
)


@pytest.mark.django_db
def test_thin_source_is_processed_without_any_llm_call():
    product = _shoe("rule-thin-shoe", "Torex BUCKY 6FX Beyaz Erkek Sneaker")
    llm = SimpleNamespace(model="test-model", generate_content=Mock(side_effect=AssertionError("LLM не нужен")))

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    assert log.status == AIProcessingStatus.COMPLETED, get_moderation_reasons(log)
    assert float(log.cost_usd) == 0
    assert log.generated_title == "Мужские кроссовки BUCKY 6FX, белые"
    assert log.raw_llm_response["rule_content"]["description_source"] == "template"
    assert "Верх: искусственная кожа" in log.generated_description
    en = log.extracted_attributes["seo_translations"]["en"]
    assert en["generated_title"] == "BUCKY 6FX Men's Sneakers, White"
    assert en["meta_title"].startswith("BUCKY 6FX Men's Sneakers")
    dynamic = {row["slug"]: row for row in log.extracted_attributes["dynamic_attributes"]}
    assert dynamic["material"]["value_ru"] == "Искусственная кожа"
    assert dynamic["material"]["value_en"] == "Faux Leather"
    assert log.suggested_category_id is None


@pytest.mark.django_db
def test_rich_source_translated_once_then_reused_from_memory():
    first = _shoe("rule-rich-1", RICH_SOURCE)
    second = _shoe("rule-rich-2", RICH_SOURCE)
    ru = "Классические кроссовки из ПВХ: прочные и легкие. " * 4
    en = "Classic PVC sneakers that are durable and light. " * 4
    llm = SimpleNamespace(
        model="test-model",
        generate_content=Mock(return_value=_llm_result({"ru": {"generated_description": ru}, "en": {"generated_description": en}})),
    )
    generator = _generator(llm)

    first_log = generator.process_product(first.id, options={"analyze_images": False, "force": True})
    assert llm.generate_content.call_count == 1
    prompt = llm.generate_content.call_args.kwargs["user_prompt"]
    assert '"need": ["generated_description"]' in prompt
    assert "available_dynamic_attributes" not in prompt and "suggested_category" not in prompt
    assert first_log.status == AIProcessingStatus.COMPLETED, get_moderation_reasons(first_log)
    assert float(first_log.cost_usd) == pytest.approx(0.00024)

    second_log = generator.process_product(second.id, options={"analyze_images": False, "force": True})

    assert llm.generate_content.call_count == 1  # второй — из памяти
    assert second_log.raw_llm_response["rule_content"]["description_source"] == "memory"
    assert second_log.generated_description == first_log.generated_description
    assert float(second_log.cost_usd) == 0
    assert AITranslationMemory.objects.get().hits == 1


@pytest.mark.django_db
def test_memory_is_not_reused_from_moderated_log():
    first = _shoe("rule-mod-1", RICH_SOURCE)
    second = _shoe("rule-mod-2", RICH_SOURCE)
    content = {"ru": {"generated_description": "Кроссовки. " * 25}, "en": {"generated_description": "Sneakers. " * 25}}
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result(content)))
    generator = _generator(llm)
    first_log = generator.process_product(first.id, options={"analyze_images": False, "force": True})
    AIProcessingLog.objects.filter(pk=first_log.pk).update(status=AIProcessingStatus.MODERATION)

    generator.process_product(second.id, options={"analyze_images": False, "force": True})

    assert llm.generate_content.call_count == 2


@pytest.mark.django_db
def test_llm_title_fallback_requested_only_when_rules_fail():
    product = _shoe("rule-title-fallback", RICH_SOURCE)
    product.name = "Erkek Plaj Havuz Terliği"
    product.save()
    content = {
        "ru": {"generated_title": "Мужские пляжные шлепанцы", "generated_description": "Описание " * 25},
        "en": {"generated_title": "Men's Beach Slippers", "generated_description": "Description " * 25},
    }
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result(content)))

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    prompt = llm.generate_content.call_args.kwargs["user_prompt"]
    assert '"need_titles": ["ru", "en"]' in prompt
    assert log.generated_title == "Мужские пляжные шлепанцы"
    assert log.raw_llm_response["rule_content"]["title_sources"] == {"ru": "llm", "en": "llm"}


@pytest.mark.django_db
def test_medical_and_uncategorized_products_keep_full_generation():
    medicine = MedicineProduct.objects.create(name="MAJEZIK 100 MG", slug="rule-medicine")
    medicine.refresh_from_db()
    assert plan_rule_content(medicine.base_product, {"name": "MAJEZIK"}, "full") is None
    clothing = ClothingProduct.objects.create(name="Erkek Tişört", slug="rule-no-category")
    clothing.refresh_from_db()
    assert plan_rule_content(clothing.base_product, {"name": "Erkek Tişört"}, "full") is None
    shoe = _shoe("rule-categorization", RICH_SOURCE)
    assert plan_rule_content(shoe, {"name": "x"}, "categorization_only") is None


# --- ложные причины модерации ---


@pytest.mark.django_db
def test_variant_sizes_from_parser_are_not_ambiguous_and_urls_are_not_sizes():
    product = _shoe(
        "rule-variant-sizes",
        "Klasik sneaker.",
        sizes="['40', '41', '42']",
        fashion_variants=[{"sizes": [{"size": "40"}], "images": ["https://cdn/x-99-76-96.jpg"]}],
    )
    shoe = product.domain_item
    variant = ShoeVariant.objects.create(product=shoe, name="Белые", slug="rule-variant-white", color="Beyaz")
    for size in ("40", "41", "42"):
        ShoeVariantSize.objects.create(variant=variant, size=size)

    sizes = extract_sizes_from_input({"name": product.name, "attributes": product.external_data["attributes"]}, "shoes")

    assert [row["size"] for row in sizes] == ["40", "41", "42"]
    assert size_inventory_block_reason(shoe, "shoes", sizes) == ""
    assert size_inventory_block_reason(shoe, "shoes", sizes + [{"size": "43"}]) == "ambiguous_variant_sizes"


@pytest.mark.django_db
def test_audience_category_is_not_a_title_conflict():
    Category.objects.create(name="Мужские", slug="rule-men")
    product = _shoe("rule-audience", RICH_SOURCE)

    report = SemanticValidator().validate(
        product, generated_titles={"ru": "Мужские кроссовки BUCKY 6FX"}, dynamic_attributes=[]
    )

    assert "title_category_mismatch" not in report.reasons


@pytest.mark.parametrize(
    "name, product_type, category_slug, attrs, ru, en",
    [
        (
            "BREAKNET 3.0 Beyaz Erkek Sneaker - Серый",  # FLO дописывает русский цвет
            "shoes",
            "sneakers",
            {"gender": "men"},
            "Мужские кроссовки BREAKNET 3.0, белые",
            "BREAKNET 3.0 Men's Sneakers, White",
        ),
        (
            "2'Lİ PAKET KOMBİN POPLİN BOXER - çeşitli",
            "underwear",
            "uw-mens-underwear",
            {"gender": "men"},
            "Мужские трусы-боксеры из поплина, 2 шт.",
            "Men's Poplin Boxers, 2-Pack",
        ),
        (
            "Bisiklet Yaka Baskılı Beyaz Erkek T-Shirt J5SM-TST7325",  # код вырезается санитайзером
            "clothing",
            "t-shirts",
            {},
            "Мужская футболка с круглым вырезом с принтом, белая",
            "Men's Crew Neck Printed T-Shirt, White",
        ),
        (
            "PLATSA/SMÅSTAD",
            "furniture",
            "wardrobes",
            {"furniture_type": "PLATSA/SMÅSTAD gardırop", "color": "beyaz"},
            "Гардероб PLATSA/SMÅSTAD, белый",
            "PLATSA/SMÅSTAD Wardrobe, white",
        ),
    ],
)
def test_titles_for_production_edge_cases(name, product_type, category_slug, attrs, ru, en):
    product = SimpleNamespace(product_type=product_type, category=SimpleNamespace(slug=category_slug), domain_item=None)
    facts = collect_facts(product, {"name": name, "brand": "Другое", "attributes": attrs})
    assert build_titles(facts) == {"ru": ru, "en": en}


def test_brand_is_taken_only_from_the_start_of_description():
    product = SimpleNamespace(product_type="accessories", category=SimpleNamespace(slug="belts"), domain_item=None)
    facts = collect_facts(
        product,
        {
            "name": "Kemer - Markalar - 499,99 TL",
            "brand": "LC Waikiki",
            "description": "%100 Suni Deri, Siyah, Rugan Suni Deri Klasik Kemer",
            "attributes": {"gender": "men"},
        },
    )
    assert facts.brand == ""
    assert build_titles(facts)["ru"] == "Мужской ремень"


def test_hyphen_codes_are_not_required_title_identity():
    from apps.ai.services.semantic_validator import _identity_tokens

    assert _identity_tokens("Bisiklet Yaka Beyaz Erkek T-Shirt J5SM-TST7325 BUCKY 6FX") == {"BUCKY", "6FX"}


@pytest.mark.django_db
def test_identity_ignores_generic_uppercase_words_and_case():
    category = Category.objects.create(name="Пояса и ремни", slug="rule-belts")
    product = SimpleNamespace(name="Kemer - LC WAIKIKI - 199,99 TL", product_type="accessories", category=category, domain_item=None)
    report = SemanticValidator().validate(
        product, generated_titles={"ru": "Мужской ремень LC Waikiki, черный"}, dynamic_attributes=[]
    )
    assert "title_identity_lost" not in report.reasons

    tee = SimpleNamespace(name="Siyah Erkek T-Shirt JORX90 TEE SS CREW", product_type="clothing", category=category, domain_item=None)
    report = SemanticValidator().validate(tee, generated_titles={"ru": "Мужская футболка, черная"}, dynamic_attributes=[])
    assert "title_identity_lost" in report.reasons  # модель JORX90/CREW потеряна


@pytest.mark.django_db
def test_color_is_left_to_variant_titles_when_product_has_variants():
    product = _shoe("rule-variant-color", "Torex BUCKY 6FX Beyaz Erkek Sneaker")
    ShoeVariant.objects.create(product=product.domain_item, name="Белые", slug="rule-variant-color-w", color="Beyaz")

    facts = collect_facts(product, {"name": product.name, "brand": "Другое", "attributes": {"color": "Beyaz"}})

    assert facts.color is None
    assert build_titles(facts)["ru"] == "Мужские кроссовки BUCKY 6FX"


def _russian_belt(slug):
    from apps.catalog.models import AccessoryProduct

    category = Category.objects.get_or_create(slug="belts", defaults={"name": "Пояса и ремни"})[0]
    brand = Brand.objects.get_or_create(name="LC Waikiki", defaults={"slug": "lc-waikiki-rule"})[0]
    belt = AccessoryProduct.objects.create(
        name="Кожаный ремень LC Waikiki",
        slug=slug,
        description=(
            "<p>Кожаный ремень от LC Waikiki выполнен из искусственной кожи коричневого цвета с "
            "серебристой застежкой. Уход за изделием: нельзя стирать, гладить и сушить в барабане.</p>"
        ),
        category=category,
        brand=brand,
    )
    belt.refresh_from_db()
    product = belt.base_product
    product.external_data = {"attributes": {"gender": "men", "material": "Искусственная кожа", "color": "Koyu Kahverengi"}}
    product.save()
    product.refresh_from_db()
    return product


@pytest.mark.django_db
def test_russian_name_gets_rule_english_title_and_survives_missing_en_from_llm():
    """Пилот 18.10: модель вернула только RU-описание — лог падал целиком."""
    product = _russian_belt("rule-ru-belt")
    ru = "Ремень LC Waikiki из искусственной кожи коричневого цвета с серебристой застежкой."
    llm = SimpleNamespace(
        model="test-model",
        generate_content=Mock(return_value=_llm_result({"ru": {"generated_description": ru}, "en": {}})),
    )

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    assert log.status == AIProcessingStatus.COMPLETED, get_moderation_reasons(log)
    prompt = llm.generate_content.call_args.kwargs["user_prompt"]
    # EN-название просим у модели (перевод русского), без ответа — правилами.
    assert '"need_titles": ["en"]' in prompt
    en = log.extracted_attributes["seo_translations"]["en"]
    assert en["generated_title"] == "LC Waikiki Men's Faux Leather Belt"
    assert en["generated_description"].startswith("LC Waikiki Men's Faux Leather Belt. Material: faux leather.")
    assert en["meta_title"] == "LC Waikiki Men's Faux Leather Belt — buy with delivery from Turkey"
    assert log.raw_llm_response["rule_content"]["description_fallback"] == ["en"]
    assert not AITranslationMemory.objects.exists()  # неполный перевод не запоминаем
    # 12 слов — короче прежнего порога 20, но это пересказ короткого источника
    assert "short_description" not in get_moderation_reasons(log)


@pytest.mark.django_db
def test_empty_llm_answer_falls_back_to_fact_descriptions_instead_of_failing():
    product = _russian_belt("rule-ru-belt-empty")
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result({"ru": {}, "en": {}})))

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    assert log.status != AIProcessingStatus.FAILED
    assert log.generated_description.startswith("Кожаный ремень LC Waikiki. Материал: искусственная кожа.")
    assert log.raw_llm_response["rule_content"]["description_fallback"] == ["ru", "en"]


@pytest.mark.django_db
def test_rule_path_fails_only_when_nothing_russian_can_be_built():
    from apps.ai.services.rules.pipeline import validate_rule_content

    with pytest.raises(ValueError, match="ru.generated_title, ru.generated_description"):
        validate_rule_content({"ru": {}, "en": {"generated_title": "X", "generated_description": "Y"}})
    validate_rule_content({"ru": {"generated_title": "Ремень", "generated_description": "Описание"}, "en": {}})


# --- артикулы, бренды маркетплейса, типы мебели (25.10.2026) ---


def _titles(name, product_type, brand="", category_slug="", attrs=None, description=""):
    product = SimpleNamespace(product_type=product_type, category=SimpleNamespace(slug=category_slug), domain_item=None)
    facts = collect_facts(product, {"name": name, "brand": brand, "attributes": attrs or {}, "description": description})
    return facts, build_titles(facts)


@pytest.mark.parametrize(
    "name, ru",
    [
        ("Erkek T Shirt LV04RF822G UB1", "Мужская футболка"),
        ("Kırmızı Erkek Tişört 4974", "Мужская футболка, красная"),
        ("238276 5FX Siyah Erkek Sneaker", "Мужские кроссовки, черные"),
        ("Pembe Erkek Normal Logo Baskılı T-Shirt 12295132 JPRBLUFELIX SS TEE", "Мужская футболка JPRBLUFELIX с логотипом, розовая"),
    ],
)
def test_supplier_codes_are_not_in_titles(name, ru):
    product_type = "shoes" if "Sneaker" in name else "clothing"
    assert _titles(name, product_type)[1]["ru"] == ru


@pytest.mark.parametrize(
    "name, category, brand, ru, en",
    [
        (
            "TUDORS Siyah Erkek Kemer - S000081236-19351",
            "belts",
            "TUDORS",
            "Мужской ремень TUDORS, черный",
            "TUDORS Men's Belt, Black",
        ),
        (
            "Loris 50 ml Erkek Parfüm - S000465805-26865",
            "perfumery",
            "Loris",
            "Мужской парфюм Loris, 50 мл",
            "Loris Men's Perfume, 50 ml",
        ),
        (
            "Altınyıldız Classics Kahverengi Erkek Kemer - S000527512-19413",
            "belts",
            "Altinyildiz Classics",
            "Мужской ремень Altinyildiz Classics, коричневый",
            "Altinyildiz Classics Men's Belt, Brown",
        ),
        (
            "LCW ACCESSORIES Dark Black Edp Erkek Parfüm 100 Ml - W53552Z8-M0T",
            "perfumery",
            "LC Waikiki",
            "Мужская парфюмерная вода LC Waikiki Dark Black, 100 мл",
            "LC Waikiki Dark Black Men's Eau de Parfum, 100 ml",
        ),
        (
            "LCW ACCESSORIES Siyah Düz Erkek Kemer - W6CG82Z8-HUC",
            "belts",
            "LC Waikiki",
            "Мужской ремень LC Waikiki, черный",
            "LC Waikiki Men's Belt, Black",
        ),
    ],
)
def test_marketplace_store_brand_is_replaced_by_brand_from_name(name, category, brand, ru, en):
    product_type = "perfumery" if category == "perfumery" else "accessories"
    facts, titles = _titles(name, product_type, brand="LC Waikiki", category_slug=category)
    assert facts.brand == brand
    assert titles == {"ru": ru, "en": en}


def test_store_own_products_keep_store_brand_and_descriptive_start_is_not_a_brand():
    facts, titles = _titles("Bisiklet Yaka Kısa Kollu Erkek Tişört", "clothing", brand="LC Waikiki", category_slug="t-shirts")
    assert facts.brand == "LC Waikiki"
    assert titles["ru"] == "Мужская футболка LC Waikiki с круглым вырезом с коротким рукавом"
    # Бренд берётся из названия только у магазина-маркетплейса.
    assert _titles("TUDORS Siyah Erkek Kemer", "accessories", brand="Zara", category_slug="belts")[0].brand == "Zara"


def test_polo_collar_is_a_descriptor_not_a_polo_shirt():
    titles = _titles("Erkek Polo Yaka %100 Pamuk Tişört", "clothing", category_slug="t-shirts")[1]
    assert titles["ru"] == "Мужская футболка с отложным воротником из хлопка"
    assert titles["en"] == "Men's Polo Collar Cotton T-Shirt"


def test_brand_from_description_drops_turkish_possessive_suffix():
    assert _brand_from_description("238545 5FX Mavi Erkek Sneaker", "Dockers by Gerli’nin 238545 5FX Mavi Erkek Sneaker") == "Dockers by Gerli"


def test_furniture_type_from_ikea_subtitle_and_unknown_type_goes_to_llm():
    _, titles = _titles("KOMPLEMENT", "furniture", brand="IKEA", category_slug="wardrobes", description="<h3>tel sepet, beyaz</h3><p>…</p>")
    assert titles == {"ru": "Проволочная корзина IKEA KOMPLEMENT", "en": "IKEA KOMPLEMENT Wire Basket"}
    # Тип IKEA, которого нет в словаре, не подменяется типом категории («Гардероб»).
    facts, titles = _titles("SKUBB", "furniture", brand="IKEA", category_slug="wardrobes", description="<h3>kılıflı kutu, beyaz</h3>")
    assert facts.kind is None and titles == {"ru": "", "en": ""}
    # Подзаголовка нет — тип по категории, как раньше.
    assert _titles("LASTARE", "furniture", brand="IKEA", category_slug="wardrobes")[1]["ru"] == "Гардероб IKEA LASTARE"


def test_seo_title_drops_color_before_short_form_and_skips_title_in_lead():
    titles = {"ru": "Мужские солнцезащитные очки Zara прямоугольной формы, коричневые", "en": ""}
    description = {"ru": "Мужские солнцезащитные очки Zara прямоугольной формы. Цвет: коричневый. Оправа из ацетата."}
    seo = build_seo(_facts("DİKDÖRTGEN GÜNEŞ GÖZLÜĞÜ", "accessories"), titles, description)["ru"]
    assert seo["seo_title"] == "Мужские солнцезащитные очки Zara прямоугольной формы из Турции"
    assert seo["seo_description"].endswith("с доставкой. Оправа из ацетата.")


def test_accessory_material_from_source_line_beats_parser_attribute():
    product = SimpleNamespace(product_type="accessories", category=SimpleNamespace(slug="belts"), domain_item=None, id=1)
    source = (
        "Siyah Erkek kemer, dokulu bir tasarıma sahiptir. Ayarlanabilir yapısı ve metal tokası ile kullanım kolaylığı sağlar. "
        "Ürün İçeriği ve Özellikleri Kumaş: Suni DeriDesen: Düz"
    )
    data = {"name": "LCW ACCESSORIES Siyah Düz Erkek Kemer - S6BV14Z8-CVL", "brand": "LC Waikiki", "description": source,
            "attributes": {"material": "Металл", "accessory_type": "belts", "gender": "men"}}
    facts = collect_facts(product, data)
    assert build_titles(facts)["ru"] == "Мужской ремень LC Waikiki из искусственной кожи, черный"
    rows = {row["slug"]: (row["value_ru"], row["value_en"]) for row in _dynamic_attributes(product, data, facts)}
    assert rows["material"] == ("Искусственная кожа", "Faux Leather")
    assert rows["accessory-type"] == ("Ремень", "Belt")


@pytest.mark.django_db
def test_source_codes_and_type_words_are_not_required_title_identity():
    category = Category.objects.create(name="Аксессуары", slug="rule-acc")
    for name, title in (
        ("Erkek T Shirt LV04RF822G UB1", "Мужская футболка"),
        ("DİKDÖRTGEN GÜNEŞ GÖZLÜĞÜ", "Солнцезащитные очки Zara прямоугольной формы"),
        ("LCW ACCESSORIES Siyah Düz Erkek Kemer - W6AQ42Z8-HUC", "Мужской ремень LC Waikiki, черный"),
        ("AMBER MELT EDT 100ML (3.4 FL.OZ)", "Туалетная вода Zara AMBER MELT, 100 мл"),
    ):
        product = SimpleNamespace(name=name, product_type="accessories", category=category, domain_item=None)
        report = SemanticValidator().validate(product, generated_titles={"ru": title}, dynamic_attributes=[])
        assert "title_identity_lost" not in report.reasons, name


@pytest.mark.django_db
def test_llm_title_with_turkish_word_falls_back_to_rule_title_without_it():
    product = _shoe("rule-title-turkish", RICH_SOURCE)
    product.name = "Barcelona Urban Haki Erkek Bilekli Günlük Sandalet 5003"
    product.save()
    content = {
        "ru": {"generated_title": "Мужские сандалии Barcelona Urban Bilekli 5003", "generated_description": "Описание " * 25},
        "en": {"generated_title": "Barcelona Urban LV04RF822G Men's Sandals", "generated_description": "Description " * 25},
    }
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result(content)))

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    # RU от модели с непереведённым «Bilekli» заменено названием правилами, из EN убран артикул.
    assert log.generated_title == "Мужские сандалии Barcelona Urban, цвета хаки"
    en = log.extracted_attributes["seo_translations"]["en"]["generated_title"]
    assert en == "Barcelona Urban Men's Sandals"
    assert log.raw_llm_response["rule_content"]["title_sources"] == {"ru": "rules", "en": "llm"}


def _perfume(slug, name, description, brand="AVON"):
    category = Category.objects.get_or_create(slug="perfumery", defaults={"name": "Парфюмерия"})[0]
    brand_obj = Brand.objects.get_or_create(name=brand, defaults={"slug": f"{slug}-brand"})[0]
    return Product.objects.create(
        name=name, slug=slug, product_type="perfumery", category=category, brand=brand_obj, description=description,
        external_data={"attributes": {"color": "Bronz", "gender": "men"}},
    )


PERFUME_SOURCE = (
    "Elite Gentleman Quest Erkek Parfüm 75 ml. Üst nota zencefil, orta nota kahve yağı esansı, "
    "alt nota sedir ağacı. Baharatlı ve odunsu bir koku."
)


@pytest.mark.django_db
@pytest.mark.parametrize("fragrance, expected", [("Elite Gentleman Quest", "Мужской парфюм AVON Elite Gentleman Quest, 75 мл"), ("Black Opium", "Мужской парфюм AVON, 75 мл")])
def test_perfume_title_gets_fragrance_name_only_when_it_is_in_source(fragrance, expected):
    product = _perfume(f"rule-perfume-{fragrance[:5].lower()}", "AVON 75 ml Erkek Parfüm - S000433876-10231", PERFUME_SOURCE)
    content = {
        "ru": {"generated_description": "Пряный древесный аромат: имбирь, кофе, кедр. " * 3},
        "en": {"generated_description": "Spicy woody scent: ginger, coffee, cedar. " * 3},
        "fragrance_name": fragrance,
    }
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result(content)))

    log = _generator(llm).process_product(product.id, options={"analyze_images": False, "force": True})

    assert '"fragrance_name"' in llm.generate_content.call_args.kwargs["user_prompt"]
    # Цвет флакона («Bronz») в название парфюма не идёт; выдуманное название аромата — тоже.
    assert log.generated_title == expected


def test_descriptive_store_names_do_not_turn_turkish_words_into_model():
    facts, titles = _titles("Teknik naylon pantolon", "clothing", brand="Bershka", category_slug="trousers")
    assert facts.model == "" and "Teknik" in facts.untranslated
    assert titles == {"ru": "", "en": ""}
    assert build_titles(facts, ignore_untranslated=True)["ru"] == "Брюки Bershka"
    assert _titles("STWD logolu boxy tişört", "clothing", brand="Pull&Bear", category_slug="t-shirts")[0].model == "STWD"


@pytest.mark.django_db
def test_kind_of_own_subcategory_is_not_a_conflict_even_if_other_tree_has_it():
    shoes = Category.objects.create(name="Обувь", slug="rule-shoes-root")
    Category.objects.create(name="Кроссовки", slug="rule-sneakers", parent=shoes)
    sports = Category.objects.create(name="Спорт", slug="rule-sports")
    Category.objects.create(name="Кроссовки", slug="rule-sports-sneakers", parent=sports)
    product = SimpleNamespace(name="GALAXY RUN Beyaz Erkek Koşu Ayakkabısı", product_type="shoes", category=shoes, domain_item=None)
    report = SemanticValidator().validate(product, generated_titles={"ru": "Мужские кроссовки Adidas GALAXY RUN"}, dynamic_attributes=[])
    assert "title_category_mismatch" not in report.reasons


def test_russian_name_keeps_text_adds_brand_and_turkish_leftovers_go_to_llm():
    assert _titles("Кепка с вышивкой", "headwear", brand="Zara", category_slug="hw-caps")[1]["ru"] == "Кепка с вышивкой Zara"
    facts, titles = _titles("Мужские боксеры Soft Boxer 3'lü Paket", "underwear", brand="Zara", category_slug="uw-mens-underwear")
    assert titles["ru"] == ""
    assert facts.model == "Soft Boxer Paket"
    assert _titles("Мужские боксеры SOFT BOXER 3'ЛЮ ПАКЕТ", "underwear", brand="Zara", category_slug="uw-mens-underwear")[1]["ru"] == ""
    assert _titles("Мужские боксеры 3 в 1", "underwear", brand="Zara", category_slug="uw-mens-underwear")[0].model == ""


def test_zip_and_turquoise_words_and_dimensions():
    titles = _titles("Turkuaz Fermuar Detaylı Erkek Tişört 4489", "clothing", category_slug="t-shirts")[1]
    assert titles["ru"] == "Мужская футболка с молнией, бирюзовая"
    from apps.ai.services.rules.facts import is_supplier_code

    assert not is_supplier_code("13x10x6") and is_supplier_code("12295132")


def test_hyphenated_words_without_digits_are_not_codes():
    from apps.catalog.utils.variant_titles import strip_price_and_codes_from_title

    assert strip_price_and_codes_from_title("GLENN 5FX Men's Slip-Ons") == "GLENN 5FX Men's Slip-Ons"
    assert strip_price_and_codes_from_title("IKEA VIMLE 3-Seat Sofa-Bed") == "IKEA VIMLE 3-Seat Sofa-Bed"
    assert strip_price_and_codes_from_title("Bisiklet Yaka T-Shirt J5SM-TST7325") == "Bisiklet Yaka T-Shirt"
    facts, titles = _titles("SPIDER-MAN reglan kısa kollu t-shirt", "clothing", brand="Bershka", category_slug="t-shirts")
    assert facts.model == "SPIDER-MAN"


def test_llm_russian_title_starting_with_brand_gets_type_first():
    from apps.ai.services.rules.pipeline import _checked_llm_title

    facts = ProductFacts(product_type="furniture")
    assert _checked_llm_title("IKEA KOMPLEMENT угловые петли с доводчиком, серые", facts, "ru") == (
        "Угловые петли с доводчиком IKEA KOMPLEMENT, серые"
    )
    assert _checked_llm_title("Pull&Bear бомбер с мехом", facts, "ru") == "Бомбер с мехом Pull&Bear"
    assert _checked_llm_title("Сабо Frozen Elsa Classic детские", facts, "ru") == "Сабо Frozen Elsa Classic детские"
    assert _checked_llm_title("IKEA VIMLE 3-Seat Sofa-Bed", facts, "ru") == ""
    assert _checked_llm_title("Мужские боксеры Zara Soft Boxer 3'lü Paket", facts, "ru") == ""


def test_single_letter_size_is_not_model():
    assert _titles("PC-7315 M Kahve Erkek Sandalet", "shoes", category_slug="sandals")[0].model == ""


def test_russian_one_letter_words_survive_code_cleanup():
    from apps.ai.services.rules.facts import drop_codes

    title = "Угловой диван-кровать IKEA BÅRSLÖV с ящиком для хранения в чехле и пуфом"
    assert " ".join(drop_codes(title.split())) == title
    assert drop_codes(["Sandalet", "M", "Kahve"]) == ["Sandalet", "Kahve"]
