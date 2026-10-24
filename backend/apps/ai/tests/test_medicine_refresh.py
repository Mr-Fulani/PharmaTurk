"""Пересчёт названия и SEO опубликованных лекарств кодом (TD-028): ручные правки не трогаются."""

import json

import pytest
from django.core.management import call_command

from apps.ai.models import AIProcessingLog
from apps.ai.services.medicine_refresh import latest_applied_log, plan_refresh
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

    changes, new = plan_refresh(product, latest_applied_log(product.id), generator)
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
