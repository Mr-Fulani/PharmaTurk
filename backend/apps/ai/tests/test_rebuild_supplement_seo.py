"""Пересборка SEO БАДов кодом из AI-логов, без модели (ревью #333)."""

import json

import pytest
from django.core.management import call_command

from apps.ai.services import supplement_seo_refresh as refresh
from apps.ai.tests.test_supplement_content import ANSWER, _generator, _process, _supplement

OLD_TITLE = "Мега-Фарма (MEGA-FARMA) Бетаглюкан — купить из Турции (старый шаблон)"


def _processed_with_old_seo():
    """БАД после обработки, как будто SEO на сайте записал старый шаблон: в логе и на карточке одно и то же."""
    supplement = _supplement()
    generator = _generator([ANSWER])
    log = _process(generator, supplement)
    generator.apply_log_to_product(log)
    attrs = dict(log.extracted_attributes)
    seo = dict(attrs["seo_translations"])
    seo["ru"] = {**seo["ru"], "meta_title": OLD_TITLE}
    attrs["seo_translations"] = seo
    log.extracted_attributes = attrs
    log.save(update_fields=["extracted_attributes"])
    supplement.refresh_from_db()
    ru = supplement.translations.get(locale="ru")
    ru.meta_title = OLD_TITLE
    ru.meta_description = "Ручное описание модератора."
    ru.save()
    return supplement, log


def test_title_brand_takes_line_number_from_name():
    assert refresh.title_brand("HIPP", "HIPP 2 Органическая смесь, 300 г", "Органическая смесь") == "HIPP 2"
    assert refresh.title_brand("SOLGAR", "SOLGAR Омниум, 60 таблеток", "Омниум") == "SOLGAR"
    # Число — начало «что это», а не линейки.
    assert refresh.title_brand("REFERANS", "REFERANS 5-HTP, 30 капсул", "5-HTP") == "REFERANS"


@pytest.mark.django_db
def test_rebuild_rewrites_logged_seo_and_keeps_manual_edits(tmp_path):
    supplement, log = _processed_with_old_seo()
    name_before = supplement.translations.get(locale="ru").name

    changes, new, skipped = refresh.plan_seo(supplement.base_product)
    assert skipped == ""
    labels = {(type(change.obj).__name__, change.locale, change.field) for change in changes}
    assert ("SupplementProductTranslation", "ru", "meta_title") in labels
    # Ручное описание модератора не перезаписывается.
    assert ("SupplementProductTranslation", "ru", "meta_description") not in labels

    backup = tmp_path / "before.json"
    call_command("rebuild_supplement_seo", "--ids", str(supplement.base_product.id), "--apply", "--backup", str(backup))
    ru = supplement.translations.get(locale="ru")
    assert ru.meta_title == new["ru"]["meta_title"] != OLD_TITLE
    assert ru.meta_description == "Ручное описание модератора."
    assert ru.name == name_before  # название (H1) не меняется
    log.refresh_from_db()
    assert log.extracted_attributes["seo_translations"]["ru"]["meta_title"] == ru.meta_title
    assert "supplement_seo_rebuilt_at" in log.extracted_attributes
    assert json.loads(backup.read_text())

    # Повтор — менять нечего.
    assert refresh.plan_seo(supplement.base_product)[0] == []

    call_command("rebuild_supplement_seo", "--restore", str(backup))
    assert supplement.translations.get(locale="ru").meta_title == OLD_TITLE


@pytest.mark.django_db
def test_rebuild_skips_when_name_is_not_from_any_log():
    supplement, _log = _processed_with_old_seo()
    ru = supplement.translations.get(locale="ru")
    ru.name = "Название, исправленное вручную"
    ru.save()
    changes, new, skipped = refresh.plan_seo(supplement.base_product)
    assert (changes, new, skipped) == ([], None, "название не из лога")


@pytest.mark.django_db
def test_rebuild_requires_backup_and_target():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("rebuild_supplement_seo", "--all", "--apply")
    with pytest.raises(CommandError):
        call_command("rebuild_supplement_seo")
