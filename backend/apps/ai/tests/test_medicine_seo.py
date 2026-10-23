from apps.ai.services.medicine_seo import (
    SEO_DESCRIPTION_MAX,
    SEO_TITLE_MAX,
    build_medicine_seo,
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
