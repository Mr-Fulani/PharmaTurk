"""Пересчёт названия и SEO опубликованных лекарств кодом (TD-028): ручные правки и то, что
у кода вышло бы хуже, не трогаются."""

import json

import pytest
from django.core.management import call_command

from apps.ai.models import AIProcessingLog
from apps.ai.services.medicine_refresh import _ingredient_stems, latest_applied_log, plan_refresh, worse_reasons
from apps.ai.services.medicine_seo import BRAND_NAMESPACE
from apps.ai.services.translation_memory import remember
from apps.ai.tests.test_medicine_code_pipeline import PARA_A, TRANSLATIONS, RecordingLLM, _generator
from apps.catalog.models import Category, MedicineProduct, MedicineProductTranslation

pytestmark = pytest.mark.django_db


def _published_majezik():
    """Лекарство, обработанное и применённое, — затем «откат» его SEO к старому коду."""
    category = Category.objects.create(name="Обезболивающие", slug="refresh-painkillers")
    medicine = MedicineProduct.objects.create(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        slug="majezik-refresh",
        category=category,
        dosage_form="tablet",
        active_ingredient="Flurbiprofen",
        prescription_type="Beyaz Reçete",
        external_data={"attributes": {"source_tabs": {"usage_instructions": {"text": PARA_A}}}},
    )
    medicine.refresh_from_db()
    card = {
        locale: {
            "generated_description": "MAJEZIK — таблетки с флурбипрофеном 100 мг." if locale == "ru"
            else "MAJEZIK film-coated tablets with flurbiprofen 100 mg.",
            "seo_title": "x", "seo_description": "x", "keywords": ["MAJEZIK"],
        }
        for locale in ("ru", "en")
    }
    llm = RecordingLLM(
        card=card,
        inn={"flurbiprofen": ("флурбипрофен", "flurbiprofen")},
        paragraphs={PARA_A.strip(): tuple(t.strip() for t in TRANSLATIONS[PARA_A.strip()])},
    )
    generator = _generator(llm)
    generator._should_use_images_for_product = lambda _product: False
    log = generator.process_product(medicine.base_product.id, options={"analyze_images": False, "force": True})
    generator.apply_log_to_product(AIProcessingLog.objects.get(pk=log.pk))
    log = AIProcessingLog.objects.get(pk=log.pk)
    # Как было до PR #167: SEO от модели, без бренда кириллицей.
    attrs = log.extracted_attributes
    attrs["seo_translations"]["ru"].update(meta_title="MAJEZIK 100 мг таблетки", og_title="MAJEZIK 100 мг таблетки")
    log.extracted_attributes = attrs
    log.save(update_fields=["extracted_attributes"])
    ru = MedicineProductTranslation.objects.get(product=medicine, locale="ru")
    ru.meta_title = ru.og_title = "MAJEZIK 100 мг таблетки"
    ru.save(update_fields=["meta_title", "og_title"])
    # Ручная правка после обработки — пересчёт её не трогает.
    en = MedicineProductTranslation.objects.get(product=medicine, locale="en")
    en.meta_description = "Hand-written EN description"
    en.save(update_fields=["meta_description"])
    return medicine


def test_refresh_rewrites_what_processing_wrote_and_keeps_manual_edits(tmp_path):
    remember(BRAND_NAMESPACE, {"MAJEZIK": {"ru": "Мажезик", "en": "MAJEZIK"}})
    medicine = _published_majezik()
    product = medicine.base_product
    generator = _generator(None)

    changes, new, kept = plan_refresh(product, latest_applied_log(product.id), generator)
    assert kept == []
    labels = {change.label for change in changes}
    assert "MedicineProductTranslation[ru].meta_title" in labels
    assert "MedicineProductTranslation[en].meta_description" not in labels

    backup = tmp_path / "before.json"
    call_command("medicine_refresh_code_fields", "--ids", str(product.id), "--apply", "--backup", str(backup))

    ru = MedicineProductTranslation.objects.get(product=medicine, locale="ru")
    en = MedicineProductTranslation.objects.get(product=medicine, locale="en")
    assert ru.meta_title == ru.og_title == "Мажезик (MAJEZIK, флурбипрофен) 100 мг, таблетки из Турции"
    assert en.meta_description == "Hand-written EN description"
    assert any(row["fields"].get("meta_title") == "MAJEZIK 100 мг таблетки" for row in json.loads(backup.read_text()))
    product = type(product).objects.select_related("medicine_item").get(pk=product.pk)
    assert product.name == "MAJEZIK (флурбипрофен) 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт."
    # Повторный пересчёт — без изменений: лог хранит новые значения.
    assert plan_refresh(product, latest_applied_log(product.id), generator)[0] == []


def test_refresh_without_apply_changes_nothing(capsys):
    medicine = _published_majezik()
    call_command("medicine_refresh_code_fields", "--ids", str(medicine.base_product.id))
    assert MedicineProductTranslation.objects.get(product=medicine, locale="ru").meta_title == "MAJEZIK 100 мг таблетки"
    assert "Только показ" in capsys.readouterr().out


@pytest.mark.parametrize(
    "field, locale, old, new, reasons",
    [
        # Брак просмотра 01.11.2026: турецкое описание набора вместо русского.
        (
            "name", "ru", "BRAIN-SPECT радиофармацевтический набор для приготовления раствора, 6 флаконов",
            "BRAIN-SPECT RADYOFARMASOTIK HAZIRLAMA KITI, 6 флаконов", ["форма", "латиница вместо перевода"],
        ),
        # SEO без формы: «из Турции — инструкция, цена» вместо «суспензия для инъекций».
        (
            "meta_title", "ru", "RISPERDAL CONSTA 25 мг суспензия для инъекций из Турции",
            "RISPERDAL CONSTA 25 мг из Турции — инструкция, цена", ["форма", "путь введения"],
        ),
        # Вещество было, пропало; бренд RISPERDAL веществом не считается.
        (
            "meta_title", "en", "RISPERDAL CONSTA 50 mg injection suspension — risperidone, from Turkey",
            "RISPERDAL CONSTA 50 mg injection suspension from Turkey", ["вещество"],
        ),
        # Вторая дозировка и форма пропали, вместо формы — латиница.
        (
            "name", "ru", "SERETIDE 100 мкг/50 мкг 60 доз, порошок для ингаляций",
            "SERETIDE (салметерол + флутиказон) 100 мкг DISKUS, 60 доз",
            ["форма", "путь введения", "дозировка", "латиница вместо перевода"],
        ),
        ("name", "ru", "MILUPA GA 1, порошок для приготовления раствора, 500 г", "MILUPA GA 1 500 г",
         ["форма", "нет русского описания"]),
        # Не хуже: та же дозировка другой записью, вещество и форма на месте, фасовки в SEO нет.
        (
            "name", "ru", "PEN-OS 1.000.000 МЕ таблетки, покрытые пленочной оболочкой (24 таблетки)",
            "PEN-OS (феноксиметилпенициллин) 1000000 МЕ, таблетки, покрытые плёночной оболочкой, 24 шт.", [],
        ),
        (
            "name", "ru", "RISPERDAL CONSTA 37,5 мг суспензия для внутримышечных инъекций",
            "RISPERDAL CONSTA (рисперидон) 37,5 мг, суспензия пролонгированного высвобождения для инъекций (в/м)", [],
        ),
        ("name", "ru", "TERRAMYCIN 30 мг + 10 000 МЕ, мазь", "TERRAMYCIN 30 мг/10000 МЕ, мазь", []),
        ("name", "ru", "HIBOR 7500 МЕ/0,3 мл, раствор для инъекций, 2 шприца", "HIBOR 7500 МЕ/0,3 мл, 2 шприца",
         ["форма", "путь введения"]),
        # Ревью PR #287: основа формы пропала, а путь введения остался.
        ("name", "ru", "AMARGINE 5 г/10 мл, раствор для инъекций, 10 ампул", "AMARGINE 5 г/10 мл, для инъекций, 10 ампул",
         ["форма"]),
        # Путь введения сменился: «ENJEKTABL SOL» шаблон переводит дословно, «IM/IV INFUZYON» — без инъекций.
        ("name", "ru", "BIOFLEKS IZOMIX 1/3 раствор для инфузий 500 мл", "BIOFLEKS IZOMIX 1/3, раствор для инъекций, 500 мл",
         ["путь введения"]),
        ("name", "ru", "GENTHAVER 160 мг раствор для инъекций и инфузий, 1 ампула",
         "GENTHAVER 160 мг, раствор для инфузий (в/м, в/в), 1 ампула", ["путь введения"]),
        # МНН нет в памяти: вещество узнаётся по изотопу.
        ("meta_title", "en", "MOLTEK FDG fludeoxyglucose (18F) injection solution from Turkey",
         "MOLTEK FDG, solution for injection, vial (IV) from Turkey", ["вещество"]),
        ("meta_title", "en", "SERODERM 0.1% ointment 30 g with betamethasone from Turkey",
         "SERODERM (betamethasone) 0.1%, ointment from Turkey — leaflet, price", []),
        ("name", "ru", "IMMUNATE 500 МЕ, порошок, флакон", "IMMUNATE (фактор свёртывания крови VIII) 500 МЕ, порошок, флакон", []),
        ("name", "ru", "", "BIOFLEKS 5%, раствор декстрозы, 1000 мл", []),
        # Пилот PR #287: пропало число штук.
        ("name", "ru", "PEKUTIN 10 мг, таблетки, 30 шт.", "PEKUTIN 10 мг, таблетки", ["фасовка"]),
        ("name", "ru", "DIAKSI 5 мг/2,5 мл раствор для ректального введения, 5 шт.",
         "DIAKSI 5 мг/2,5 мл, раствор для ректального введения", ["фасовка"]),
        ("name", "ru", "SEPTIX 5 мг/1 мг лимонные пастилки (20 пастилок)", "SEPTIX 5 мг/1 мг, пастилки, со вкусом лимона, 20 шт.", []),
        ("name", "en", "MOLTEK FDG solution for intravenous injection, 1 vial", "MOLTEK FDG, solution for injection, vial (IV), 1 pc", []),
        ("name", "en", "IC-GREEN 25 mg, 6 ampoules of 10 ml", "IC-GREEN 25 mg, ampoules, 6 × 10 ml", []),
    ],
)
def test_worse_reasons(field, locale, old, new, reasons):
    ingredient = _ingredient_stems("Risperidon", "Betametazon", "рисперидон", "risperidone", "betamethasone")
    brand = "RISPERDAL CONSTA" if old.startswith("RISPERDAL") else ""
    assert worse_reasons(field, locale, old, new, ingredient, brand) == reasons


def test_turkish_kit_words_give_no_code_title():
    code = _generator(None)._build_medicine_code_fields(
        {"name": "BRAIN-SPECT RADYOFARMASOTIK HAZIRLAMA KITI 6 FLAKON"}, allow_llm=False
    )
    assert code["title"] is None


def test_refresh_keeps_worse_name_and_still_writes_seo(tmp_path, capsys):
    """Новое название теряет вторую дозировку — название остаётся, SEO пишется; лог названия не меняется."""
    remember(BRAND_NAMESPACE, {"MAJEZIK": {"ru": "Мажезик", "en": "MAJEZIK"}})
    medicine = _published_majezik()
    product = medicine.base_product
    detailed = {"ru": "MAJEZIK 100 мг/25 мг, таблетки, 15 шт.", "en": "MAJEZIK 100 mg/25 mg tablets, 15 pcs"}
    log = latest_applied_log(product.id)
    attrs = log.extracted_attributes
    for locale in ("ru", "en"):
        attrs["seo_translations"][locale]["generated_title"] = detailed[locale]
    log.extracted_attributes = attrs
    log.generated_title = detailed["ru"]
    log.save(update_fields=["extracted_attributes", "generated_title"])
    product.name = medicine.name = detailed["ru"]
    product.save(update_fields=["name"])
    medicine.save(update_fields=["name"])
    for translation in medicine.translations.filter(locale__in=("ru", "en")):
        translation.name = detailed[translation.locale]
        translation.save(update_fields=["name"])

    product = type(product).objects.select_related("medicine_item").get(pk=product.pk)
    changes, _new, kept = plan_refresh(product, latest_applied_log(product.id), _generator(None))
    assert kept == ["название: дозировка"]
    assert changes and all(change.field != "name" for change in changes)

    call_command(
        "medicine_refresh_code_fields", "--ids", str(product.id), "--apply", "--backup", str(tmp_path / "b.json")
    )
    out = capsys.readouterr().out
    assert '"оставлено: новое хуже": 1' in out and '"оставлено, название: дозировка": 1' in out
    ru = MedicineProductTranslation.objects.get(product=medicine, locale="ru")
    assert ru.name == detailed["ru"]
    assert ru.meta_title == "Мажезик (MAJEZIK, флурбипрофен) 100 мг, таблетки из Турции"
    log = latest_applied_log(product.id)
    assert log.generated_title == detailed["ru"]
    assert log.extracted_attributes["seo_translations"]["ru"]["meta_title"] == ru.meta_title
