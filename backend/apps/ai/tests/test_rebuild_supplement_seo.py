"""Пересборка SEO БАДов кодом из AI-логов, без модели (ревью #333)."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.services import supplement_content as sc
from apps.ai.services import supplement_seo_refresh as refresh
from apps.ai.tests.test_supplement_content import ANSWER, _generator, _process, _supplement
from apps.catalog.models import Product

OLD_TITLE = "Мега-Фарма (MEGA-FARMA) Бетаглюкан — купить из Турции (старый шаблон)"
OLD_TITLE_EN = "MEGA-FARMA Beta-Glucan — old template"


def _processed_with_old_seo(slug="mega-farma-betaglukan"):
    """БАД после обработки, как будто SEO на сайте записал старый шаблон: в логе и на карточке одно и то же."""
    supplement = _supplement(slug=slug)
    generator = _generator([ANSWER])
    log = _process(generator, supplement)
    generator.apply_log_to_product(log)
    attrs = dict(log.extracted_attributes)
    seo = dict(attrs["seo_translations"])
    seo["ru"] = {**seo["ru"], "meta_title": OLD_TITLE, "og_title": OLD_TITLE}
    seo["en"] = {**seo["en"], "meta_title": OLD_TITLE_EN, "og_title": OLD_TITLE_EN}
    attrs["seo_translations"] = seo
    log.extracted_attributes = attrs
    log.save(update_fields=["extracted_attributes"])
    supplement.refresh_from_db()
    for locale, title in (("ru", OLD_TITLE), ("en", OLD_TITLE_EN)):
        supplement.translations.filter(locale=locale).update(meta_title=title, og_title=title)
    type(supplement).objects.filter(pk=supplement.pk).update(meta_title=OLD_TITLE_EN, og_title=OLD_TITLE_EN)
    return supplement, log


def _seo_state(supplement, log):
    supplement.refresh_from_db()
    log.refresh_from_db()
    rows = {
        locale: {f: getattr(tr, f) for f in refresh.SEO_FIELDS}
        for locale, tr in ((tr.locale, tr) for tr in supplement.translations.all())
    }
    product = Product.objects.filter(pk=supplement.base_product_id).values(*refresh.PRODUCT_SEO_FIELDS).first()
    return {
        "domain": {f: getattr(supplement, f) for f in refresh.SEO_FIELDS},
        "translations": rows,
        "product": product,
        "log_seo": log.extracted_attributes["seo_translations"],
        "log_title": log.generated_seo_title,
        "log_rebuilt": log.extracted_attributes.get("supplement_seo_rebuilt_at"),
    }


def test_title_brand_takes_line_number_from_name():
    assert refresh.title_brand("HIPP", "HIPP 2 Органическая смесь, 300 г", "Органическая смесь") == "HIPP 2"
    assert refresh.title_brand("SOLGAR", "SOLGAR Омниум, 60 таблеток", "Омниум") == "SOLGAR"
    # Число — начало «что это», а не линейки.
    assert refresh.title_brand("REFERANS", "REFERANS 5-HTP, 30 капсул", "5-HTP") == "REFERANS"


@pytest.mark.django_db
def test_rebuild_writes_new_seo_and_restore_returns_everything(tmp_path):
    supplement, log = _processed_with_old_seo()
    pid = supplement.base_product_id
    name_before = supplement.translations.get(locale="ru").name
    before = _seo_state(supplement, log)

    backup = tmp_path / "before.jsonl"
    call_command("rebuild_supplement_seo", "--ids", str(pid), "--apply", "--backup", str(backup))
    after = _seo_state(supplement, log)
    assert after["translations"]["ru"]["meta_title"].startswith("Мега-Фарма (MEGA-FARMA) Бетаглюкан")
    assert after["translations"]["ru"]["meta_title"] != OLD_TITLE
    assert after["translations"]["en"]["meta_title"] != OLD_TITLE_EN
    assert after["domain"]["meta_title"] == after["translations"]["en"]["meta_title"]
    # Product — копия SEO домена, как при синхронизации.
    assert after["product"]["meta_title"] == after["product"]["seo_title"] == after["domain"]["meta_title"]
    assert after["log_seo"]["ru"]["meta_title"] == after["translations"]["ru"]["meta_title"]
    assert after["log_rebuilt"]
    assert supplement.translations.get(locale="ru").name == name_before  # название (H1) не меняется
    # Повтор — менять нечего.
    assert refresh.run([pid])[0]["уже как в коде"] == 1

    # Ревью #333, п. 4: в бэкапе только SEO-поля, без описания и цены.
    rows = [json.loads(line) for line in backup.read_text().splitlines()]
    keys = {key for row in rows for key in row["fields"]}
    assert keys <= set(refresh.PRODUCT_SEO_FIELDS) | {"seo_translations", "generated_seo_title", "supplement_seo_rebuilt_at"}

    # Ревью #333, п. 2: возвращается всё — RU, EN, домен, Product и SEO лога.
    call_command("rebuild_supplement_seo", "--restore", str(backup))
    assert _seo_state(supplement, log) == before
    # П. 5: текущее состояние перед возвратом сохранено.
    snapshots = list(tmp_path.glob("before.jsonl.before-restore-*.jsonl"))
    assert len(snapshots) == 1 and snapshots[0].read_text().strip()
    # После возврата значения снова «из лога» — следующий прогон их перепишет, а не сочтёт ручными.
    assert refresh.run([pid])[0]["к изменению"] == 1


@pytest.mark.django_db
def test_rebuild_does_not_roll_back_fields_written_meanwhile(tmp_path):
    """Ревью #333, п. 3: пишутся только SEO-поля через update(), без save() и синхронизации домена."""
    supplement, _log = _processed_with_old_seo()
    pid = supplement.base_product_id
    Product.objects.filter(pk=pid).update(price=999, stock_quantity=7, description="<p>Описание парсера.</p>")
    call_command("rebuild_supplement_seo", "--ids", str(pid), "--apply", "--backup", str(tmp_path / "b.jsonl"))
    product = Product.objects.get(pk=pid)
    assert (product.price, product.stock_quantity, product.description) == (999, 7, "<p>Описание парсера.</p>")


@pytest.mark.django_db
def test_rebuild_skips_when_moderator_edited_title():
    """Ревью #333, п. 1: части лога — ответ модели; правку названия модератором они не знают."""
    supplement, log = _processed_with_old_seo()
    edited = "MEGA-FARMA Бетаглюкан с цинком, сироп, 150 мл"
    attrs = dict(log.extracted_attributes)
    attrs["seo_translations"] = {**attrs["seo_translations"], "ru": {**attrs["seo_translations"]["ru"], "generated_title": edited}}
    log.extracted_attributes = attrs
    log.save(update_fields=["extracted_attributes"])
    supplement.translations.filter(locale="ru").update(name=edited)
    stats, _examples = refresh.run([supplement.base_product_id])
    assert stats["пропущено: название правлено"] == 1


@pytest.mark.django_db
def test_rebuild_skips_when_name_is_not_from_any_log():
    supplement, _log = _processed_with_old_seo()
    supplement.translations.filter(locale="ru").update(name="Название, исправленное вручную")
    stats, _examples = refresh.run([supplement.base_product_id])
    assert stats["пропущено: название не из лога"] == 1


@pytest.mark.django_db
def test_manual_field_keeps_whole_object(tmp_path):
    """Ревью #333, п. 6: правлено одно поле — объект остаётся целиком (иначе og_title ≠ meta_title)."""
    supplement, _log = _processed_with_old_seo()
    supplement.translations.filter(locale="ru").update(og_title="Заголовок модератора")
    stats, _examples = refresh.run([supplement.base_product_id], apply=True, backup=open(tmp_path / "b.jsonl", "w"))
    assert stats["объектов правлено вручную (оставлены)"] == 1
    ru = supplement.translations.get(locale="ru")
    assert (ru.meta_title, ru.og_title) == (OLD_TITLE, "Заголовок модератора")
    assert supplement.translations.get(locale="en").meta_title != OLD_TITLE_EN


@pytest.mark.django_db
def test_rebuild_goes_in_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "BATCH_SIZE", 1)
    first, _ = _processed_with_old_seo("mega-farma-1")
    second, _ = _processed_with_old_seo("mega-farma-2")
    with open(tmp_path / "b.jsonl", "w") as backup:
        stats, _examples = refresh.run([first.base_product_id, second.base_product_id], apply=True, backup=backup)
    assert stats["записано"] == 2


def test_usage_paragraph_with_markup_and_zma():
    assert sc.has_usage_paragraph('<p class="usage"><strong>Способ применения:</strong> 1 капсула в день.</p>')
    assert sc.has_usage_paragraph("<p><b>Способ применения</b>: 1 капсула.</p>")
    assert not sc.has_usage_paragraph("<p><strong>Состав:</strong> магний.</p>")
    assert sc._block_wording("магний, цинк (Zma)") == "магний, цинк (ZMA)"


@pytest.mark.django_db
def test_rebuild_requires_backup_and_target():
    with pytest.raises(CommandError):
        call_command("rebuild_supplement_seo", "--all", "--apply")
    with pytest.raises(CommandError):
        call_command("rebuild_supplement_seo")


@pytest.mark.django_db
def test_existing_backup_and_snapshot_are_not_overwritten(tmp_path):
    """Ревью #333 (третье), п. 1: перезапуск с тем же --backup не теряет прежнее SEO, двойной возврат —
    два снимка."""
    supplement, _log = _processed_with_old_seo()
    pid = str(supplement.base_product_id)
    backup = tmp_path / "before.jsonl"
    call_command("rebuild_supplement_seo", "--ids", pid, "--apply", "--backup", str(backup))
    content = backup.read_text()
    with pytest.raises(CommandError, match="уже есть"):
        call_command("rebuild_supplement_seo", "--ids", pid, "--apply", "--backup", str(backup))
    assert backup.read_text() == content
    call_command("rebuild_supplement_seo", "--restore", str(backup))
    call_command("rebuild_supplement_seo", "--restore", str(backup))
    assert len(list(tmp_path.glob("before.jsonl.before-restore-*.jsonl"))) == 2


@pytest.mark.django_db
def test_backup_reaches_disk_before_each_batch_commits(tmp_path, monkeypatch):
    """П. 2: flush + fsync бэкапа внутри транзакции пачки — после OOM хвост записанной пачки не теряется."""
    from django.db import transaction

    monkeypatch.setattr(refresh, "BATCH_SIZE", 1)
    calls = []
    monkeypatch.setattr(refresh.os, "fsync", lambda fd: calls.append(transaction.get_connection().in_atomic_block))
    first, _ = _processed_with_old_seo("mega-farma-1")
    second, _ = _processed_with_old_seo("mega-farma-2")
    with open(tmp_path / "b.jsonl", "w") as backup:
        refresh.run([first.base_product_id, second.base_product_id], apply=True, backup=backup)
    # Тест сам идёт в транзакции, поэтому проверяется, что fsync — по разу на пачку и внутри неё.
    assert len(calls) == 2 and all(calls)


@pytest.mark.django_db
def test_restore_returns_values_byte_for_byte(tmp_path):
    """П. 3: пробелы по краям — как были; сравнение с логом их не учитывает."""
    supplement, _log = _processed_with_old_seo()
    spaced = f"  {OLD_TITLE} "
    supplement.translations.filter(locale="ru").update(meta_title=spaced)
    backup = tmp_path / "before.jsonl"
    call_command("rebuild_supplement_seo", "--ids", str(supplement.base_product_id), "--apply", "--backup", str(backup))
    assert supplement.translations.get(locale="ru").meta_title != spaced
    call_command("rebuild_supplement_seo", "--restore", str(backup))
    assert supplement.translations.get(locale="ru").meta_title == spaced


@pytest.mark.django_db
def test_rebuild_bumps_updated_at_for_sitemap(tmp_path):
    """П. 4: lastmod sitemap БАДов — SupplementProduct.updated_at; update() его сам не трогает."""
    from datetime import timedelta

    from django.utils import timezone

    supplement, _log = _processed_with_old_seo()
    past = timezone.now() - timedelta(days=30)
    type(supplement).objects.filter(pk=supplement.pk).update(updated_at=past)
    Product.objects.filter(pk=supplement.base_product_id).update(updated_at=past)
    call_command(
        "rebuild_supplement_seo", "--ids", str(supplement.base_product_id), "--apply", "--backup", str(tmp_path / "b.jsonl")
    )
    supplement.refresh_from_db()
    assert supplement.updated_at > past
    assert Product.objects.get(pk=supplement.base_product_id).updated_at > past


def _with_legacy_delivery(supplement, log):
    """Лог до 28.10: «доставка 7–21 рабочий день»; на сайте — та же строка после замены в базе на «7–14 дней»."""
    site = "Мега-Фарма (MEGA-FARMA) Бетаглюкан из Турции. Заявка менеджеру, доставка 7–14 дней."
    logged = site.replace("доставка 7–14 дней", "доставка 7–21 рабочий день")
    attrs = dict(log.extracted_attributes)
    seo = dict(attrs["seo_translations"])
    seo["ru"] = {**seo["ru"], "meta_description": logged, "og_description": logged}
    attrs["seo_translations"] = seo
    log.extracted_attributes = attrs
    log.generated_seo_description = logged
    log.save(update_fields=["extracted_attributes", "generated_seo_description"])
    supplement.translations.filter(locale="ru").update(meta_description=site, og_description=site)


@pytest.mark.django_db
def test_legacy_delivery_edit_is_auto_only_with_flag(tmp_path):
    """07.11: 5 333 объекта остались со старым SEO — 28.10 срок доставки заменён прямо в базе, в логах прежний."""
    supplement, log = _processed_with_old_seo()
    _with_legacy_delivery(supplement, log)
    pid = supplement.base_product_id
    assert refresh.run([pid])[0]["объектов правлено вручную (оставлены)"] == 1
    stats, _examples = refresh.run([pid], legacy_as_auto=True)
    assert stats["объектов правлено вручную (оставлены)"] == 0 and stats["к изменению"] == 1
    call_command(
        "rebuild_supplement_seo", "--ids", str(pid), "--treat-legacy-as-auto", "--apply", "--backup", str(tmp_path / "b.jsonl")
    )
    assert supplement.translations.get(locale="ru").meta_title != OLD_TITLE
    # Настоящая ручная правка остаётся и с флагом.
    supplement.translations.filter(locale="ru").update(meta_description="Ручное описание модератора.")
    assert refresh.run([pid], legacy_as_auto=True)[0]["объектов правлено вручную (оставлены)"] == 1


@pytest.mark.django_db
def test_admin_history_seo_edit_protects_product_with_flag():
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.contrib.auth import get_user_model
    from django.contrib.contenttypes.models import ContentType

    supplement, log = _processed_with_old_seo()
    _with_legacy_delivery(supplement, log)
    pid = supplement.base_product_id
    user = get_user_model().objects.create(username="moderator", email="moderator@example.com")

    def edit(fields):
        LogEntry.objects.create(
            user=user, content_type=ContentType.objects.get_for_model(type(supplement)), object_id=str(supplement.pk),
            object_repr="x", action_flag=CHANGE,
            change_message=json.dumps([{"changed": {"name": "Перевод БАДа", "object": "x", "fields": fields}}]),
        )

    edit(["Цена"])  # не SEO — не мешает
    assert refresh.run([pid], legacy_as_auto=True)[0]["к изменению"] == 1
    edit(["Meta Title"])
    stats, _examples = refresh.run([pid], legacy_as_auto=True)
    assert stats["пропущено: SEO правлено в админке"] == 1
    # Без флага история админки не читается — поведение прежнее.
    assert refresh.run([pid])[0]["пропущено: SEO правлено в админке"] == 0
