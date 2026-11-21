"""Турецкие буквы в названии и SEO лекарств и БАДов → обычные латинские (показ по умолчанию).

Бренд источника с турецкими буквами («LONGİVO», «VİTAPUFF») попадал в название и SEO как
есть: «LONGİVO» ≠ «LONGIVO», по латинице карточка хуже находится в Google. С 21.11.2026
сборка названия пишет бренд латиницей (``medicine_reference.latin_tr``); команда
исправляет карточки, записанные раньше.

    manage.py latinize_turkish_names                          # показ: было → станет
    manage.py latinize_turkish_names --ids 13115,9416         # только эти записи (pk Product)
    manage.py latinize_turkish_names --apply --backup /backups/latinize.json

Правило: İ→I, ı→i, Ş→S, ş→s, Ğ→G, ğ→g, Ç→C, ç→c, Ö→O, ö→o, Ü→U, ü→u. Поля: название,
meta/og title и description, ключевые слова — у записи лекарства или БАДа, её переводов,
базового Product и его переводов; то же в последнем применённом логе обработки (иначе
``medicine_refresh_code_fields`` считал бы название исправленным вручную и больше его не
обновлял). Запись — через update(), без сигналов.

Не трогаются: название источника (external_data["source_name"]), адрес карточки (slug),
описания и инструкции; скрытые карточки (is_active=False); карточки без переводов — у них
в названии турецкий оригинал целиком, им нужна обработка, а не замена букв.

После записи — rebuild_product_search_index --ids <id,…> --apply (строку с id печатает команда).

Откат: для каждой строки бэкапа — Model.objects.filter(pk=…).update(**fields).
"""
import json

from django.apps import apps
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ai.services.medicine_reference import latin_tr
from apps.ai.services.medicine_refresh import latest_applied_log
from apps.catalog.models import MedicineProduct, Product, ProductTranslation, SupplementProduct
from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX

TURKISH_RE = "[İıŞşĞğÇçÖöÜü]"
FIELDS = ("name", "meta_title", "meta_description", "og_title", "og_description", "meta_keywords")
PRODUCT_FIELDS = FIELDS + ("seo_title", "seo_description", "keywords")
LOG_FIELDS = ("generated_title", "generated_seo_title", "generated_seo_description", "generated_keywords")
# В логе рядом с названием и SEO лежит описание — его не меняем.
_LOG_SEO_SKIP = {"generated_description"}


def latinize(value):
    """latin_tr для строки, списка и словаря; остальное — как есть."""
    if isinstance(value, str):
        return latin_tr(value)
    if isinstance(value, list):
        return [latinize(item) for item in value]
    if isinstance(value, dict):
        return {key: latinize(item) for key, item in value.items()}
    return value


def _any_field(prefix: str = "") -> Q:
    query = Q()
    for field in FIELDS:
        query |= Q(**{f"{prefix}{field}__regex": TURKISH_RE})
    return query


def _changed(obj, fields) -> dict:
    """{поле: новое значение} для полей, где есть турецкие буквы."""
    result = {}
    for field in fields:
        old = getattr(obj, field)
        new = latinize(old)
        if new != old:
            result[field] = new
    return result


def _log_changes(log) -> dict:
    result = _changed(log, LOG_FIELDS)
    attrs = log.extracted_attributes if isinstance(log.extracted_attributes, dict) else {}
    seo = attrs.get("seo_translations")
    if isinstance(seo, dict):
        new_seo = {
            locale: (
                {key: value if key in _LOG_SEO_SKIP else latinize(value) for key, value in entry.items()}
                if isinstance(entry, dict) else entry
            )
            for locale, entry in seo.items()
        }
        if new_seo != seo:
            result["extracted_attributes"] = {**attrs, "seo_translations": new_seo}
    return result


class Command(BaseCommand):
    help = "Турецкие буквы в названии и SEO лекарств и БАДов → латинские. Без --apply только показ."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument("--ids", default="", help="pk Product через запятую (по умолчанию все).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        try:
            ids = [int(part) for part in options["ids"].split(",") if part.strip()]
        except ValueError as exc:
            raise CommandError("--ids: только числа через запятую") from exc

        plan = []  # (объект, {поле: новое})
        product_ids, slugs = [], []
        skipped = {"скрытые": 0, "без переводов (турецкий оригинал)": 0}
        self.stdout.write("раздел | id Product | название: было → станет | полей")
        for model, label in ((MedicineProduct, "лекарства"), (SupplementProduct, "БАДы")):
            query = (
                _any_field() | _any_field("translations__")
                | _any_field("base_product__") | _any_field("base_product__translations__")
            )
            records = model.objects.filter(query).distinct().order_by("pk")
            if ids:
                records = records.filter(base_product_id__in=ids)
            for record in records.select_related("base_product").prefetch_related("translations"):
                translations = list(record.translations.all())
                if not record.is_active:
                    skipped["скрытые"] += 1
                    continue
                if not translations:
                    skipped["без переводов (турецкий оригинал)"] += 1
                    continue
                product = record.base_product
                targets = [(record, FIELDS)] + [(row, FIELDS) for row in translations]
                if product:
                    targets.append((product, PRODUCT_FIELDS))
                    targets += [(row, FIELDS) for row in ProductTranslation.objects.filter(product=product)]
                rows = [(obj, _changed(obj, fields)) for obj, fields in targets]
                rows = [(obj, changes) for obj, changes in rows if changes]
                if not rows:
                    continue
                log = latest_applied_log(product.pk) if product else None
                if log and _log_changes(log):
                    rows.append((log, _log_changes(log)))
                plan += rows
                if product:
                    product_ids.append(product.pk)
                    slugs.append(product.slug)
                name = next(
                    (row.name for row in translations if row.locale == "ru" and row.name), record.name
                )
                self.stdout.write(
                    f"{label} | {product.pk if product else '—'} | {name} → {latin_tr(name)} | "
                    f"{sum(len(changes) for _obj, changes in rows)}"
                )
        self.stdout.write(
            f"Итого карточек: {len(product_ids)}, записей: {len(plan)}. Не тронуто: "
            + ", ".join(f"{key} — {value}" for key, value in skipped.items())
        )
        if product_ids:
            self.stdout.write("Индекс поиска: --ids " + ",".join(map(str, product_ids)))
        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        backup = [
            {
                "model": obj._meta.label, "pk": obj.pk,
                "fields": {field: getattr(obj, field) for field in changes},
            }
            for obj, changes in plan
        ]
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1)
        now = timezone.now()
        with transaction.atomic():
            for obj, changes in plan:
                values = dict(changes)
                # Дата изменения — для sitemap; у лога она не нужна.
                if isinstance(obj, (Product, MedicineProduct, SupplementProduct)):
                    values["updated_at"] = now
                apps.get_model(obj._meta.label).objects.filter(pk=obj.pk).update(**values)
        for slug in slugs:
            cache.delete(RESOLVE_CACHE_PREFIX + slug)
        self.stdout.write(self.style.SUCCESS(
            f"Записано карточек: {len(product_ids)}, записей: {len(plan)}. Бэкап: {options['backup']}"
        ))
