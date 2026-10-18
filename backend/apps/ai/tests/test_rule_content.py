"""Детерминированные тексты не медицинских товаров: LLM только как fallback."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.rules import vocab
from apps.ai.services.rules.facts import ProductFacts, clean_source_text, collect_facts, parse_name
from apps.ai.services.rules.pipeline import plan_rule_content
from apps.ai.services.rules.text import build_fact_description, build_seo, build_titles, is_thin_source
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import extract_sizes_from_input, size_inventory_block_reason
from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    MedicineProduct,
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
            "Мужская футболка с круглым вырезом с коротким рукавом с принтом",
            "Men's Crew Neck Short Sleeve Printed T-Shirt",
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
    assert seo["ru"]["seo_description"] == "Заказать Мужские кроссовки BUCKY 6FX, белые из Турции. Легкие кроссовки из ПВХ."
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
