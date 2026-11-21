"""Турецкие буквы бренда в названии и SEO лекарств и БАДов — латиницей.

21.11.2026: у 46 лекарств и 4 БАДов на сайте стояло «LONGİVO», «VİTAPUFF» — как в источнике.
По латинице («LONGIVO») такие карточки хуже находятся. Сборка названия пишет бренд
латиницей, команда latinize_turkish_names исправляет записанное раньше.
"""

import json

import pytest
from django.core.management import CommandError, call_command

from apps.ai.models import AIProcessingLog
from apps.ai.services import supplement_content as sc
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_reference import latin_tr
from apps.ai.services.medicine_title import build_medicine_title, paragraph_brand, title_brand, title_with_inn
from apps.catalog.models import (
    Category,
    MedicineProduct,
    MedicineProductTranslation,
    Product,
    ProductTranslation,
)

COMMAND = "latinize_turkish_names"
SOURCE = "LONGİVO 5 MG TABLET (28 ADET)"
RU = "LONGİVO (тадалафил) 5 мг, таблетки, 28 шт."
EN = "LONGİVO (tadalafil) 5 mg, tablets, 28 pcs"
RU_FIXED = "LONGIVO (тадалафил) 5 мг, таблетки, 28 шт."
EN_FIXED = "LONGIVO (tadalafil) 5 mg, tablets, 28 pcs"


def test_latin_tr_keeps_case_and_other_text():
    assert latin_tr("İBUMENT ışık ŞĞÇÖÜ şğçöü") == "IBUMENT isik SGCOU sgcou"
    assert latin_tr("LEVOTIRON 100 мкг, таблетки") == "LEVOTIRON 100 мкг, таблетки"
    # «İ» в нижнем регистре — «i» с комбинируемой точкой (U+0307).
    assert latin_tr("longi̇vo") == "longivo"


def test_medicine_title_writes_brand_in_latin():
    title = build_medicine_title(SOURCE)
    assert title == {"ru": "LONGIVO 5 мг, таблетки, 28 шт.", "en": "LONGIVO 5 mg, tablets, 28 pcs"}
    assert title_brand(SOURCE) == "LONGIVO"
    # МНН встаёт после бренда — бренд названия и бренд шаблона совпадают.
    assert title_with_inn(title, SOURCE, ("тадалафил", "tadalafil"), "Tadalafil") == {"ru": RU_FIXED, "en": EN_FIXED}
    # Метка {BRAND} памяти абзацев — как в источнике: ключи готовых переводов не меняются.
    assert paragraph_brand(SOURCE) == "LONGİVO"


def test_supplement_title_and_seo_write_brand_in_latin():
    assert sc.assemble_title("VİTAPUFF", "Витамин B12, спрей", "", "ru") == "VITAPUFF Витамин B12, спрей"
    seo = sc.build_seo("METİLMAX", "", {"ru": "Витамин B12", "en": "Vitamin B12"}, None)
    for locale in ("ru", "en"):
        assert "İ" not in json.dumps(seo[locale], ensure_ascii=False)
        assert "METILMAX" in seo[locale]["seo_title"].upper()


@pytest.mark.parametrize("product_type", ["medicines", "supplements"])
def test_model_answer_is_latinized_before_saving(product_type):
    content = {
        "ru": {
            "generated_title": "PANTOLAX ACTAVİS 2% раствор", "seo_title": "PANTOLAX ACTAVİS из Турции",
            "seo_description": "PANTOLAX ACTAVİS — раствор.", "keywords": ["PANTOLAX ACTAVİS"],
            "generated_description": "<p>Производитель: Abdi İbrahim.</p>",
        },
    }
    generator = ContentGenerator.__new__(ContentGenerator)
    bucket = generator._sanitize_ai_content(content, {"product_type": product_type})["ru"]
    assert bucket["generated_title"] == "PANTOLAX ACTAVIS 2% раствор"
    assert bucket["seo_title"] == "PANTOLAX ACTAVIS из Турции"
    assert bucket["seo_description"] == "PANTOLAX ACTAVIS — раствор."
    assert bucket["keywords"] == ["PANTOLAX ACTAVIS"]
    assert "Abdi İbrahim" in bucket["generated_description"]  # описание не трогаем


# --- команда ---------------------------------------------------------------------


@pytest.fixture
def quiet_signals(monkeypatch):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


def _medicine(slug: str, **extra) -> MedicineProduct:
    category, _ = Category.objects.get_or_create(slug="latinize-meds", defaults={"name": "Лекарства"})
    values = {
        "name": RU, "slug": slug, "category": category, "meta_title": f"{EN} from Turkey",
        "external_data": {"source_name": SOURCE}, **extra,
    }
    medicine = MedicineProduct.objects.create(**values)
    medicine.refresh_from_db()
    return medicine


def _translated(slug: str, **extra) -> MedicineProduct:
    medicine = _medicine(slug, **extra)
    for locale, name in (("ru", RU), ("en", EN)):
        MedicineProductTranslation.objects.create(
            product=medicine, locale=locale, name=name, meta_title=f"{name} — Mudaroba",
            meta_keywords="LONGİVO, тадалафил", description="<p>LONGİVO — таблетки.</p>",
        )
        ProductTranslation.objects.create(product=medicine.base_product, locale=locale, name=name)
    Product.objects.filter(pk=medicine.base_product_id).update(name=RU, keywords=["LONGİVO"], seo_title=RU)
    return medicine


@pytest.mark.django_db
def test_command_shows_then_writes_with_backup(quiet_signals, tmp_path, capsys):
    medicine = _translated("longivo-5-mg")
    product = medicine.base_product
    log = AIProcessingLog.objects.create(
        product=product, processing_type="full", application_status="applied", generated_title=RU,
        input_data={"name": SOURCE},
        extracted_attributes={"seo_translations": {"ru": {
            "generated_title": RU, "meta_title": f"{RU} — Mudaroba", "generated_description": "<p>LONGİVO</p>",
        }}},
    )
    hidden = _translated("longivo-hidden", is_active=False)
    untranslated = _medicine("apiprick-source", name="APIPRICK DERİ PRİCK TESTİ")
    clean = _medicine("levotiron", name="LEVOTIRON 100 мкг", meta_title="", external_data={})

    call_command(COMMAND)
    out = capsys.readouterr().out
    assert f"{RU} → {RU_FIXED}" in out
    assert "Итого карточек: 1" in out and "скрытые — 1" in out and "без переводов (турецкий оригинал) — 1" in out
    medicine.refresh_from_db()
    assert medicine.name == RU  # показ ничего не пишет

    with pytest.raises(CommandError):
        call_command(COMMAND, "--apply")
    backup = tmp_path / "backup.json"
    call_command(COMMAND, "--apply", "--backup", str(backup))

    medicine.refresh_from_db()
    product.refresh_from_db()
    log.refresh_from_db()
    assert medicine.name == RU_FIXED and medicine.meta_title == f"{EN_FIXED} from Turkey"
    assert medicine.slug == "longivo-5-mg"
    assert medicine.external_data["source_name"] == SOURCE  # название источника — для сверки парсера
    assert product.name == RU_FIXED and product.keywords == ["LONGIVO"] and product.seo_title == RU_FIXED
    ru = MedicineProductTranslation.objects.get(product=medicine, locale="ru")
    assert ru.name == RU_FIXED and ru.meta_keywords == "LONGIVO, тадалафил"
    assert ru.description == "<p>LONGİVO — таблетки.</p>"  # описание не трогаем
    assert ProductTranslation.objects.get(product=product, locale="en").name == EN_FIXED
    # Лог — то, с чем сравнивает пересчёт названий: иначе название считалось бы ручной правкой.
    seo = log.extracted_attributes["seo_translations"]["ru"]
    assert log.generated_title == RU_FIXED and seo["generated_title"] == RU_FIXED
    assert seo["generated_description"] == "<p>LONGİVO</p>" and log.input_data == {"name": SOURCE}

    for other in (hidden, untranslated, clean):
        name = other.name
        other.refresh_from_db()
        assert other.name == name
    saved = {(row["model"], row["pk"]): row["fields"] for row in json.loads(backup.read_text(encoding="utf-8"))}
    assert saved[("catalog.MedicineProduct", medicine.pk)]["name"] == RU
    assert saved[("ai.AIProcessingLog", log.pk)]["generated_title"] == RU

    call_command(COMMAND)  # повторный показ — исправлять нечего
    assert "Итого карточек: 0" in capsys.readouterr().out


@pytest.mark.django_db
def test_command_ids_limit_the_run(quiet_signals, capsys):
    first = _translated("longivo-a")
    second = _translated("longivo-b")
    call_command(COMMAND, "--ids", str(first.base_product_id))
    out = capsys.readouterr().out
    assert "Итого карточек: 1" in out and f"--ids {first.base_product_id}\n" in out
    assert str(second.base_product_id) not in out.split("Индекс поиска")[1]
