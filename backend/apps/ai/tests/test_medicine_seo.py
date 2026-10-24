from apps.ai.services.medicine_seo import (
    SEO_DESCRIPTION_MAX,
    SEO_TITLE_MAX,
    build_medicine_seo,
    cyrillic_brand,
    fallback_seo,
    needs_cold_chain,
    prescription_kind,
)

MAJEZIK = {
    "ru": "MAJEZIK (флурбипрофен) 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт.",
    "en": "MAJEZIK (flurbiprofen) 100 mg, film-coated tablets, 15 pcs",
}


def test_seo_title_has_cyrillic_brand_inn_form_and_turkey():
    seo = build_medicine_seo(MAJEZIK, "MAJEZIK", "Мажезик", ("флурбипрофен", "flurbiprofen"), "rx")
    assert seo["ru"]["seo_title"] == "Мажезик (MAJEZIK, флурбипрофен) 100 мг, таблетки из Турции"
    assert seo["en"]["seo_title"] == "MAJEZIK (flurbiprofen) 100 mg, film-coated tablets from Turkey"
    assert seo["ru"]["seo_description"] == (
        "Мажезик (MAJEZIK, флурбипрофен) 100 мг, таблетки из Турции. Отпускается по рецепту. "
        "Инструкция на русском. Заявка менеджеру, доставка 7–21 рабочий день."
    )
    assert seo["ru"]["keywords"] == [
        "MAJEZIK", "Мажезик", "флурбипрофен", "таблетки", "Мажезик из Турции", "Мажезик инструкция",
    ]


def test_seo_fits_limits_and_drops_parts_from_the_end():
    title = {
        "ru": "SCANIX (гадодиамид) 287 мг/мл, раствор для инъекций, флакон (в/в), 20 мл",
        "en": "SCANIX (gadodiamide) 287 mg/ml, solution for injection, vial (IV), 20 ml",
    }
    seo = build_medicine_seo(title, "SCANIX", "Сканикс", ("гадодиамид", "gadodiamide"), "rx")
    for locale in ("ru", "en"):
        assert len(seo[locale]["seo_title"]) <= SEO_TITLE_MAX
        assert len(seo[locale]["seo_description"]) <= SEO_DESCRIPTION_MAX
    assert seo["ru"]["seo_title"].startswith("Сканикс (SCANIX")


def test_seo_without_dose_keeps_comma_and_without_dictionary_uses_latin():
    seo = build_medicine_seo({"ru": "ZINCO, сироп, 150 мл", "en": "ZINCO, syrup, 150 ml"}, "ZINCO", "", None, "otc")
    assert seo["ru"]["seo_title"] == "ZINCO, сироп, 150 мл из Турции — инструкция, цена"
    # Безрецептурный: о рецепте ничего, «без рецепта» не пишем (SEO-план, «Ограничения»).
    assert "рецепт" not in seo["ru"]["seo_description"]


def test_controlled_medicine_is_not_promoted():
    title = {"ru": "DUROGESIC (фентанил) 75 мкг/ч, трансдермальный пластырь, 5 шт.", "en": "DUROGESIC (fentanyl) 75 mcg/h, transdermal patch, 5 pcs"}
    seo = build_medicine_seo(title, "DUROGESIC", "Дюрогезик", ("фентанил", "fentanyl"), "controlled")
    for locale in ("ru", "en"):
        text = " ".join([seo[locale]["seo_title"], seo[locale]["seo_description"], *seo[locale]["keywords"]])
        for word in ("Турци", "Turkey", "доставка", "delivery", "цена", "price", "Заявка", "request"):
            assert word not in text
    assert "строгого учёта" in seo["ru"]["seo_description"]


def test_import_restricted_medicine_has_no_delivery_and_names_countries():
    title = {"ru": "PERGE (прегабалин) 75 мг, капсулы, 56 шт.", "en": "PERGE (pregabalin) 75 mg, capsules, 56 pcs"}
    seo = build_medicine_seo(title, "PERGE", "Перге", ("прегабалин", "pregabalin"), "rx", restricted_countries=["KZ", "RU"])
    assert seo["ru"]["seo_description"] == (
        "Перге (PERGE, прегабалин) 75 мг, капсулы из Турции. Отпускается по рецепту. "
        "Ввоз в Россию и Казахстан ограничен. Инструкция на русском."
    )
    assert "Import to Russia and Kazakhstan is restricted." in seo["en"]["seo_description"]
    assert "delivery" not in seo["en"]["seo_description"]


def test_import_restriction_always_fits_long_lead_and_controlled():
    # Пилот 6: у TYLOLHOT DAY и PAROL-K «Ввоз … ограничен» не помещался в 160 символов.
    title = {
        "ru": "TYLOLHOT DAY 500 мг + 30 мг + 2 мг/20 г, порошок для приготовления раствора для приёма внутрь, 12 саше",
        "en": "TYLOLHOT DAY 500 mg + 30 mg + 2 mg/20 g, powder for oral solution, 12 sachets",
    }
    seo = build_medicine_seo(title, "TYLOLHOT DAY", "Тилолхот Дэй", None, "rx", restricted_countries=["KZ", "RU", "UZ"])
    assert seo["ru"]["seo_description"] == (
        "Тилолхот Дэй (TYLOLHOT DAY) 500 мг + 30 мг + 2 мг/20 г из Турции. Отпускается по рецепту. "
        "Ввоз в Россию, Казахстан и Узбекистан ограничен."
    )
    title = {"ru": "PAROL-K (кодеин + парацетамол) 500 мг/10 мг, таблетки, 20 шт.",
             "en": "PAROL-K (codeine + paracetamol) 500 mg/10 mg, tablets, 20 pcs"}
    seo = build_medicine_seo(title, "PAROL-K", "Парол-К", ("кодеин + парацетамол", "codeine + paracetamol"),
                             "controlled", restricted_countries=["KZ", "RU", "UZ"])
    for locale, phrase in (("ru", "Ввоз в Россию, Казахстан и Узбекистан ограничен."),
                           ("en", "Import to Russia, Kazakhstan and Uzbekistan is restricted.")):
        description = seo[locale]["seo_description"]
        assert phrase in description and len(description) <= SEO_DESCRIPTION_MAX
        assert "строгого учёта" in seo["ru"]["seo_description"]


def test_fallback_seo_of_controlled_medicine_drops_turkey_and_order():
    seo = fallback_seo(
        "APRANAX SEMIPLUS из Турции — инструкция, цена", "APRANAX SEMIPLUS, таблетки из Турции", "ru", "controlled",
        ["KZ", "RU", "UZ"],
    )
    assert seo == {
        "seo_title": "APRANAX SEMIPLUS",
        "seo_description": "APRANAX SEMIPLUS, таблетки. Препарат строгого учёта, отпускается по специальному рецепту. "
        "Ввоз в Россию, Казахстан и Узбекистан ограничен.",
    }


def test_cold_chain_from_source_storage_text():
    assert needs_cold_chain("2°C - 8°C arasında buzdolabında saklayınız.")
    assert needs_cold_chain("2 °C ile 8 °C arasında saklayınız")
    assert needs_cold_chain("Buzdolabında saklayınız.")
    assert not needs_cold_chain("25°C altındaki oda sıcaklığında saklayınız. Buzdolabında saklamayınız.")
    seo = build_medicine_seo(MAJEZIK, "MAJEZIK", "Мажезик", ("флурбипрофен", "flurbiprofen"), "rx", cold_chain=True)
    assert "Хранение и перевозка при 2–8 °C." in seo["ru"]["seo_description"]


def test_prescription_kind_from_reference_translation():
    assert prescription_kind("prescription medicine") == "rx"
    assert prescription_kind("restricted prescription medicine") == "rx"
    assert prescription_kind("controlled prescription medicine") == "controlled"
    assert prescription_kind("over-the-counter medicine") == "otc"
    assert prescription_kind("") == ""


def test_cyrillic_brand_for_longer_and_shorter_title_brand():
    found = {
        "EXTRANEFROL PERITON DIYALIZ": {"ru": "Экстранефрол Перитонеальный Диализ"},
        "PHYSIONEAL": {"ru": "Физионеал"},
        "POLIFLEKS": {"ru": "Полифлекс"},
    }
    assert cyrillic_brand("EXTRANEFROL", "EXTRANEFROL PERITON DIYALIZ", found) == "Экстранефрол"
    assert cyrillic_brand("PHYSIONEAL 40", "PHYSIONEAL", found) == "Физионеал 40"
    # Латинский хвост кириллицей не записать — бренд в SEO латиницей.
    assert cyrillic_brand("POLIFLEKS 1/3 POLIDEKS", "POLIFLEKS", found) == ""
    assert cyrillic_brand("CAPD 4 STAY SAFE", "CAPD", found) == ""


def test_long_brand_title_falls_back_without_cutting_on_preposition():
    title = {
        "ru": "POLIFLEKS 1/3 POLIDEKS (хлорид натрия + декстроза), раствор для внутривенных инфузий, без системы, пакет, 1000 мл",
        "en": "POLIFLEKS 1/3 POLIDEKS (sodium chloride + dextrose), solution for intravenous infusion, without set, bag, 1000 ml",
    }
    seo = build_medicine_seo(title, "POLIFLEKS 1/3 POLIDEKS", "", ("хлорид натрия + декстроза", "sodium chloride + dextrose"), "rx")
    assert seo["ru"]["seo_title"] == "POLIFLEKS 1/3 POLIDEKS, раствор для внутривенных инфузий из Турции"
    # Бренд кириллицей важнее «из Турции»: «Экстранефрол (EXTRANEFROL), …» без «из Турции», а не латиницей.
    title = {
        "ru": "EXTRANEFROL, раствор для перитонеального диализа, одинарный пакет, 2500 мл",
        "en": "EXTRANEFROL, peritoneal dialysis solution, single bag, 2500 ml",
    }
    seo = build_medicine_seo(title, "EXTRANEFROL", "Экстранефрол", None, "rx")
    assert seo["ru"]["seo_title"] == "Экстранефрол (EXTRANEFROL), раствор для перитонеального диализа"
