"""БАДы: название, SEO и состав — кодом, бренд, «что это» и описание — один запрос к модели."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services import supplement_content as sc
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import Category, SupplementProduct

SOURCE = "MEGA-FARMA BETAGLUKAN SURUP KARA MURVER EKSTRESI VE CINKO ICEREN TAKVIYE EDICI GIDA 150 ml şişe"
ATTRS = {
    "manufacturer": "Mega Farma",
    "administration_route": "Oral",
    "sgk_status": "Bedeli Ödenmez",
    "shelf_life": "24 Ay",
    "origin_country": "İmal",
    "prescription_type": "Reçetesiz",
}
ANSWER = {
    "brand": "MEGA-FARMA",
    "brand_ru": "Мега-Фарма",
    "product": {
        "ru": "Бетаглюкан, экстракт чёрной бузины и цинк, сироп",
        "en": "Beta-Glucan, Black Elderberry Extract and Zinc Syrup",
    },
    "ingredients": [
        {"ru": "Бетаглюкан", "en": "Beta-glucan", "dose": ""},
        {"ru": "Экстракт чёрной бузины", "en": "Black elderberry extract", "dose": ""},
        {"ru": "Цинк", "en": "Zinc", "dose": ""},
    ],
    "serving": {"ru": "", "en": ""},
    "description": {
        "ru": [
            "MEGA-FARMA — сироп с бетаглюканом, экстрактом чёрной бузины и цинком во флаконе 150 мл. "
            "Принимается внутрь.",
            "Бетаглюкан — полисахарид, который получают из клеточных стенок дрожжей и злаков. "
            "Срок годности 24 месяца. Помогает при простуде.",
        ],
        "en": [
            "MEGA-FARMA is a syrup with beta-glucan, black elderberry extract and zinc in a 150 ml bottle. "
            "It is taken orally.",
            "Beta-glucan is a polysaccharide obtained from the cell walls of yeast and cereals.",
        ],
    },
}


def _llm_result(content, cost=0.0006):
    return {
        "content": content,
        "tokens": {"prompt": 900, "completion": 500, "total": 1400, "cached": 0},
        "cost_usd": cost,
        "processing_time_ms": 5,
        "model": "claude-haiku-5-5",
    }


def _generator(answers):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator._get_prompt_template = lambda *_args, **_kwargs: ""
    generator.llm = SimpleNamespace(
        model="test-model", generate_content=Mock(side_effect=[_llm_result(a) for a in answers])
    )
    return generator


def _supplement(name=SOURCE, slug="mega-farma-betaglukan", attrs=None):
    category, _ = Category.objects.get_or_create(slug="supplements-content", defaults={"name": "БАДы"})
    supplement = SupplementProduct.objects.create(
        name=name,
        slug=slug,
        category=category,
        external_data={"source": "ilacfiyati", "attributes": dict(attrs or ATTRS)},
    )
    supplement.refresh_from_db()
    return supplement


def _process(generator, supplement):
    log = generator.process_product(
        supplement.base_product.id, options={"analyze_images": False, "categorize": False, "force": True}
    )
    log.refresh_from_db()
    return log


# --- фасовка ---


@pytest.mark.parametrize(
    "name, ru, en",
    [
        ("SOLGAR ADVANCED MULTI FORMULA KAPSUL 30 kapsül", "30 капсул", "30 capsules"),
        ("VOONKA VONVIA FOR MEN KAPSUL 62 kapsül", "62 капсулы", "62 capsules"),
        ("X KAPSUL 21 tablet", "21 таблетка", "21 tablets"),
        (SOURCE, "150 мл", "150 ml"),
        ("INOVIT MULTIVITAMIN ICEREN EFERVESAN TABLET 20 tablet", "20 шипучих таблеток", "20 effervescent tablets"),
        ("ZADE VITAL ASPIR YAGI YUMUSAK KAPSUL 600 mg 60 kapsül/HDPE şişe", "60 мягких капсул", "60 soft capsules"),
        ("CLAUSY PROBIYOTIK - YETISKIN 10x5 ml flakon", "10 флаконов по 5 мл", "10 vials × 5 ml"),
        ("OPTIFIBRE SASE 10x5 g saşe", "10 саше по 5 г", "10 sachets × 5 g"),
        ("SMA OPTIPRO PROBIYOTIK 2 (6-12 AY) DEVAM SUTU 800 g toz", "800 г", "800 g"),
        ("OCEAN SMART GUMMIES C VITAMINI 64 çiğnenebilir jel form", "64 жевательные конфеты", "64 gummies"),
        ("LIGONE MELATONIN CIGNEME TABLET 90 tablet", "90 жевательных таблеток", "90 chewable tablets"),
        ("SIMFLOR PROBIYOTIK 10 saşe", "10 саше", "10 sachets"),
    ],
)
def test_pack_is_parsed_with_russian_agreement(name, ru, en):
    pack = sc.parse_pack(name)
    assert (pack.ru, pack.en) == (ru, en)


def test_pack_keeps_source_words_and_powder_form():
    pack = sc.parse_pack("SMA OPTIPRO PROBIYOTIK 2 (6-12 AY) DEVAM SUTU 800 g toz")
    assert pack.source == "800 g toz"
    assert (pack.form_ru, pack.form_en) == ("порошок", "powder")
    assert sc.parse_pack("MAQUATRE MAGNEZYUM COMPLEX") is None
    assert sc.parse_pack("SUPRADYN ENERGY FOCUS FILM KAPLI TABLET 30 tablet").ru == "30 покрытых оболочкой таблеток"


# --- название и SEO ---


def test_title_puts_generic_product_after_comma():
    assert sc.assemble_title("MAGNIMORE PLUS", "Пищевая добавка", "30 таблеток", "ru") == (
        "MAGNIMORE PLUS, пищевая добавка, 30 таблеток"
    )
    assert sc.assemble_title("MAGNIMORE PLUS", "Food Supplement", "30 tablets", "en") == (
        "MAGNIMORE PLUS Food Supplement, 30 tablets"
    )
    assert sc.assemble_title("SOLGAR", "витамин D3 1000 МЕ", "", "ru") == "SOLGAR Витамин D3 1000 МЕ"


def test_seo_fits_limits_and_uses_cyrillic_brand():
    seo = sc.build_seo(
        "SOLGAR", "Солгар", {"ru": "Витамин D3 1000 МЕ", "en": "Vitamin D3 1000 IU"},
        sc.parse_pack("SOLGAR VITAMIN D3 1000 IU 100 softjel"),
    )
    assert seo["ru"]["seo_title"] == "Солгар (SOLGAR) Витамин D3 1000 МЕ — купить из Турции"
    assert seo["ru"]["seo_description"].startswith("Солгар (SOLGAR) Витамин D3 1000 МЕ, 100 мягких капсул из Турции.")
    assert "Заявка менеджеру" in seo["ru"]["seo_description"]
    assert seo["en"]["seo_title"] == "SOLGAR Vitamin D3 1000 IU, 100 soft capsules — buy from Turkey"
    assert {"SOLGAR", "Солгар", "витамин D3 1000 МЕ", "Солгар из Турции"} <= set(seo["ru"]["keywords"])
    long = sc.build_seo(
        "ZADE VITAL", "Заде Витал",
        {"ru": "Омега-3, рыбий жир, витамины A, D и E, со вкусом смеси фруктов, сироп", "en": "Omega-3 Fish Oil Syrup"},
        sc.parse_pack("ZADE VITAL OMEPA 200 ml şişe"),
    )
    for locale in ("ru", "en"):
        assert len(long[locale]["seo_title"]) <= sc.SEO_TITLE_MAX
        assert len(long[locale]["seo_description"]) <= sc.SEO_DESCRIPTION_MAX
    assert long["ru"]["seo_title"].split()[-1] not in {"и", "с", "со", ","}


def test_title_problem_when_number_from_source_is_lost():
    assert sc.title_problems("REFERANS NUTRA Омега, 30 капсул", "REFERANS NUTRA OMEGA 1000 KAPSUL 30 kapsül") == [
        "supplement_title_number_lost"
    ]
    assert sc.title_problems("REFERANS NUTRA Омега 1000, 30 капсул", "REFERANS NUTRA OMEGA 1000 KAPSUL 30 kapsül") == []


# --- описание ---


def test_paragraph_drops_boilerplate_and_health_claims():
    text = "Мелатонин — гормон. Срок годности 36 месяцев. Помогает лечить бессонницу. Продаётся без рецепта."
    assert sc.clean_paragraph(text) == "Мелатонин — гормон."
    assert sc.clean_paragraph("Prevents colds. Zinc is a mineral.") == "Zinc is a mineral."


def test_description_gets_disclaimer_and_problems_are_checked():
    html = sc.build_description(["Состав: бетаглюкан."], "ru")
    assert html == f"<p>Состав: бетаглюкан.</p><p>{sc.DISCLAIMER['ru']}</p>"
    assert sc.description_problems(html, SOURCE) == []
    assert sc.description_problems("<p>Принимать 2 раза в день.</p>", SOURCE) == ["supplement_unsourced_number"]
    assert sc.description_problems("<p>Лечит простуду.</p>", SOURCE) == ["supplement_health_claim"]
    # «5x109kob» таблицы состава — 5×10⁹ КОЕ: «10» есть в источнике.
    assert sc.unsourced_numbers("5×10⁹ КОЕ и 50 мг инулина", "5x109kob İnülin 50 mg") == []


# --- обработка товара ---


@pytest.mark.django_db
def test_supplement_card_is_built_by_code_around_one_model_call():
    supplement = _supplement()
    generator = _generator([ANSWER])
    log = _process(generator, supplement)

    assert generator.llm.generate_content.call_count == 1
    call = generator.llm.generate_content.call_args.kwargs
    payload = json.loads(call["user_prompt"].split("\n", 1)[1])
    assert payload["source_name"] == SOURCE
    assert payload["pack"] == {"ru": "150 мл", "en": "150 ml", "form": None}
    assert payload["facts"] == {"route": {"ru": "внутрь", "en": "orally"}}
    assert payload["glossary"]["KARA MURVER"] == "чёрная бузина | black elderberry"
    assert "manufacturer" not in payload and "Mega Farma" not in call["user_prompt"]
    assert "sgk" not in call["user_prompt"].lower() and "24 Ay" not in call["user_prompt"]

    assert log.status == AIProcessingStatus.COMPLETED, (get_moderation_reasons(log), log.generated_title)
    assert log.generated_title == "MEGA-FARMA Бетаглюкан, экстракт чёрной бузины и цинк, сироп, 150 мл"
    seo = log.extracted_attributes["seo_translations"]
    assert seo["en"]["generated_title"] == "MEGA-FARMA Beta-Glucan, Black Elderberry Extract and Zinc Syrup, 150 ml"
    assert seo["ru"]["meta_title"].startswith("Мега-Фарма (MEGA-FARMA) Бетаглюкан")
    assert len(seo["ru"]["meta_title"]) <= 70 and len(seo["ru"]["meta_description"]) <= 160
    # Срок годности и обещание («помогает при простуде») код убрал, дисклеймер добавил.
    assert "Срок годности" not in log.generated_description, log.generated_description
    assert "простуд" not in log.generated_description
    assert log.generated_description.endswith(f"<p>{sc.DISCLAIMER['ru']}</p>")
    translations = log.extracted_attributes["translations_data"]
    assert translations["ru"]["active_ingredient"] == "Бетаглюкан, Экстракт чёрной бузины, Цинк"
    assert translations["en"]["active_ingredient"] == "Beta-glucan, Black elderberry extract, Zinc"
    assert log.raw_llm_response["rule_content"]["supplement"]["brand_ru_source"] == "llm"
    assert AITranslationMemory.objects.get(namespace=sc.BRAND_NAMESPACE, source_text="MEGA-FARMA").ru_text == "Мега-Фарма"

    generator.apply_log_to_product(log)
    supplement.refresh_from_db()
    assert supplement.name == log.generated_title
    assert supplement.external_data["source_name"] == SOURCE
    ru = supplement.translations.get(locale="ru")
    assert ru.active_ingredient == "Бетаглюкан, Экстракт чёрной бузины, Цинк"
    assert supplement.translations.get(locale="en").description.startswith("<p>MEGA-FARMA is a syrup")


@pytest.mark.django_db
def test_known_brand_comes_from_memory_and_reprocessing_uses_source_name():
    AITranslationMemory.objects.create(
        namespace=sc.BRAND_NAMESPACE, source_hash=sc.translation_memory.source_hash("MEGA-FARMA"),
        source_text="MEGA-FARMA", ru_text="Мега Фарма", en_text="MEGA-FARMA",
    )
    supplement = _supplement(name="MEGA-FARMA Бетаглюкан, сироп, 150 мл", slug="mega-farma-ru")
    AIProcessingLog.objects.create(
        product=supplement.base_product, processing_type="full", status=AIProcessingStatus.APPROVED,
        input_data={"name": SOURCE},
    )
    generator = _generator([{**ANSWER, "brand_ru": "Другое"}])
    log = _process(generator, supplement)

    payload = json.loads(generator.llm.generate_content.call_args.kwargs["user_prompt"].split("\n", 1)[1])
    assert payload["source_name"] == SOURCE
    assert payload["brand_ru"] == "Мега Фарма"
    assert log.extracted_attributes["seo_translations"]["ru"]["meta_title"].startswith("Мега Фарма (MEGA-FARMA)")
    generator.apply_log_to_product(log)
    supplement.refresh_from_db()
    assert supplement.external_data["source_name"] == SOURCE


@pytest.mark.django_db
def test_brand_that_is_not_a_source_prefix_falls_back_to_first_word():
    supplement = _supplement()
    log = _process(_generator([{**ANSWER, "brand": "Mega Farma"}]), supplement)
    assert log.generated_title.startswith("MEGA-FARMA Бетаглюкан")
    assert log.raw_llm_response["rule_content"]["supplement"]["brand_from_model"] is False


@pytest.mark.django_db
def test_untranslated_product_phrase_fails_the_log():
    supplement = _supplement()
    answer = {**ANSWER, "product": {"ru": "BETAGLUKAN SURUP", "en": "Beta-Glucan Syrup"}}
    # RU «что это» не переведено — RU-названия нет, обязательное поле → лог с ошибкой.
    with pytest.raises(ValueError, match="ru.generated_title"):
        _process(_generator([answer]), supplement)
    assert AIProcessingLog.objects.get(product=supplement.base_product).status == AIProcessingStatus.FAILED


@pytest.mark.django_db
def test_unsourced_number_keeps_description_out_of_the_card():
    supplement = _supplement()
    answer = json.loads(json.dumps(ANSWER))
    answer["description"]["ru"][1] = "Принимать по 2 чайные ложки."
    generator = _generator([answer])
    log = _process(generator, supplement)

    assert log.status == AIProcessingStatus.MODERATION
    assert "supplement_unsourced_number" in get_moderation_reasons(log)
    report = SemanticValidator().validate_log(log)
    assert "description" in report.rejected_fields

    before = supplement.description
    generator.apply_log_to_product(log)
    supplement.refresh_from_db()
    assert supplement.description == before
    assert supplement.name == log.generated_title

    log.generated_description = log.generated_description.replace("Принимать по 2 чайные ложки.", "")
    seo = log.extracted_attributes["seo_translations"]
    seo["ru"]["generated_description"] = log.generated_description
    log.save()
    assert "supplement_unsourced_number" not in get_moderation_reasons(log)


# --- словарь ингредиентов ---


def test_glossary_hints_and_checks_turkish_ingredients():
    from apps.ai.services import supplement_glossary as glossary

    name = "NEUROBOR KOENZIM Q10 VE KEREVIZ EKSTRESI ICEREN TAKVIYE EDICI GIDA"
    assert glossary.glossary_for(name) == {
        "KOENZIM Q10": "коэнзим Q10 | coenzyme Q10",
        "KEREVIZ": "сельдерей | celery",
        "EKSTRESI": "экстракт | extract",
    }
    assert glossary.found_terms("ZADE VITAL KARA MURVER EKSTRESI") == ["kara murver", "ekstresi"]
    middle = "KOENZIM Q10 VE KEREVIZ EKSTRESI"
    assert glossary.missing_terms(
        middle, "Коэнзим Q10 и экстракт конского каштана", "Coenzyme Q10 and Horse Chestnut Extract"
    ) == ["kereviz"]
    assert glossary.missing_terms(
        middle, "Коэнзим Q10 и экстракт сельдерея", "Coenzyme Q10 and Celery Extract"
    ) == []
    # Любой вариант перевода из словаря: «Black Cumin Oil» = «black seed».
    assert glossary.missing_terms("COREK OTU YAGI", "Масло чернушки", "Black Cumin Oil") == []


@pytest.mark.django_db
def test_mistranslated_glossary_word_keeps_title_out_of_the_card():
    source = "NEUROBOR KOENZIM Q10 VE KEREVIZ EKSTRESI ICEREN TAKVIYE EDICI GIDA 30 kapsül"
    supplement = _supplement(name=source, slug="neurobor")
    answer = {
        **ANSWER,
        "brand": "NEUROBOR",
        "brand_ru": "Нейробор",
        "product": {"ru": "Коэнзим Q10 и экстракт конского каштана", "en": "Coenzyme Q10 and Horse Chestnut Extract"},
        "description": {"ru": ["NEUROBOR — капсулы с коэнзимом Q10."], "en": ["NEUROBOR — capsules with coenzyme Q10."]},
    }
    generator = _generator([answer])
    log = _process(generator, supplement)

    payload = json.loads(generator.llm.generate_content.call_args.kwargs["user_prompt"].split("\n", 1)[1])
    assert payload["glossary"]["KEREVIZ"] == "сельдерей | celery"
    assert "supplement_ingredient_mistranslated" in get_moderation_reasons(log)
    assert "title" in SemanticValidator().validate_log(log).rejected_fields


@pytest.mark.parametrize(
    "latin, cyrillic, ok",
    [
        ("SOLGAR", "Солгар", True),
        ("I-COLL", "Ай-Колл", True),
        ("DR.WAGNER IMMUFAST COMPLEX", "Доктор Вагнер Иммуфаст Комплекс", True),
        ("OCEAN SMART GUMMIES", "Оушен Смарт Гаммис", True),
        ("TUSPAN", "Тусбан", False),
        ("MIQRAND", "Миаранд", False),
    ],
)
def test_cyrillic_brand_must_read_like_latin(latin, cyrillic, ok):
    assert sc.transliteration_matches(latin, cyrillic) is ok


def test_repeated_pack_and_piece_form_are_cut_from_product():
    assert sc._without_piece_form("Пробиотик, 10 капсул", sc.parse_pack("X 10 kapsül"), "ru") == "Пробиотик"
    assert sc._without_piece_form("Ресвератрол и пектин, пастилки", sc.parse_pack("X 30 pastil"), "ru") == (
        "Ресвератрол и пектин"
    )
    assert sc._without_piece_form("Шипучие таблетки", sc.parse_pack("X 20 tablet"), "ru") == "пищевая добавка"
    assert sc._without_piece_form("Масло чёрного тмина", sc.parse_pack("X 30 ml"), "ru") == "Масло чёрного тмина"


def test_baby_food_gets_its_own_disclaimer_and_no_route():
    assert sc.is_baby_food("SMA OPTIPRO PROBIYOTIK 3 (1-3 YAŞ) DEVAM SÜTÜ 800 g toz")
    assert not sc.is_baby_food("SOLGAR VITAMIN D3 100 softjel")
    html = sc.build_description(["Смесь для детей от 1 года."], "ru", baby_food=True)
    assert html.endswith(f"<p>{sc.BABY_DISCLAIMER['ru']}</p>") and "Биологически активная" not in html
    assert sc._facts({"name": "APTAMIL 3 TOZ 400 G TOZ", "attributes": {"administration_route": "Oral"}}) == {
        "kind": {"ru": "детское питание", "en": "baby food"}
    }
    seo = sc.build_seo("APTAMIL", "Аптамил", {"ru": "Смесь 3", "en": "Formula 3"}, sc.parse_pack("X 400 g toz"), baby_food=True)
    assert "детское питание смесь 3" in seo["ru"]["keywords"]


def test_number_before_capsule_word_is_not_the_pack():
    from apps.ai.services.semantic_validator import _supplement_identity_tokens

    tokens = _supplement_identity_tokens("ONVITA MULTIVITAMIN & MINERALLER VE OMEGA 3 KAPSUL 30 kapsül", source=True)
    assert {t for t in tokens if t.startswith("PACK:")} == {"PACK:30"}
