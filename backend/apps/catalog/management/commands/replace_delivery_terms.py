"""Сроки доставки в SEO-описаниях лекарств и БАДов: прежние → «3–14 дней» (короткая форма; полная — «авиа 3–7, наземная 7–14, морем 20–45 дней»).

Решение владельца 09.11.2026: у лекарств и БАДов один срок, как на /delivery. Генераторы SEO
(``medicine_seo``, ``supplement_content``) уже пишут новый; эта команда правит записанные раньше
описания: «Заявка менеджеру, доставка 7–21 рабочий день.» (лекарства), «… 7–14 дней.» (БАДы) →
«Заявка менеджеру, доставка 3–14 дней.», другие формулировки срока — «3–14 дней» (описания для поиска
короткие; правила — ``apps.catalog.services.delivery_terms``). Одежду, обувь и прочие товары не трогает.

    manage.py replace_delivery_terms                     # показ: сколько записей и товаров изменится, примеры
    manage.py replace_delivery_terms --show 20           # больше примеров
    manage.py replace_delivery_terms --apply --backup /backups/delivery-terms-20261110.jsonl
    manage.py replace_delivery_terms --restore /backups/delivery-terms-20261110.jsonl

Поля: seo_description, meta_description, og_description у Product (типы medicines/supplements) и его
переводов, у MedicineProduct/SupplementProduct и их переводов. Запись — пачками в транзакции под
блокировкой строк, только изменённые поля через ``update()``: без ``save()`` и синхронизации домена,
чтобы не откатить цену и остаток, записанные парсером тем временем. Бэкап — jsonl (модель, pk, поле,
прежнее и новое значение); ``--restore`` возвращает прежнее, только если поле не меняли после записи.
Логи AI-обработки не меняются: пересборка SEO БАДов узнаёт новую строку (``supplement_seo_refresh``).
"""
import json
from collections import Counter, defaultdict

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.catalog.services.delivery_terms import replace_terms

BATCH_SIZE = 500
_DESCRIPTION_FIELDS = ("meta_description", "og_description")
# (модель, фильтр, поля, БАДы?, поле со ссылкой на Product для подсчёта товаров)
TARGETS = (
    ("catalog.Product", {"product_type": "medicines"}, ("seo_description",) + _DESCRIPTION_FIELDS, False, "id"),
    ("catalog.Product", {"product_type": "supplements"}, ("seo_description",) + _DESCRIPTION_FIELDS, True, "id"),
    ("catalog.ProductTranslation", {"product__product_type": "medicines"}, _DESCRIPTION_FIELDS, False, "product_id"),
    ("catalog.ProductTranslation", {"product__product_type": "supplements"}, _DESCRIPTION_FIELDS, True, "product_id"),
    ("catalog.MedicineProduct", {}, _DESCRIPTION_FIELDS, False, "base_product_id"),
    ("catalog.MedicineProductTranslation", {}, _DESCRIPTION_FIELDS, False, "product__base_product_id"),
    ("catalog.SupplementProduct", {}, _DESCRIPTION_FIELDS, True, "base_product_id"),
    ("catalog.SupplementProductTranslation", {}, _DESCRIPTION_FIELDS, True, "product__base_product_id"),
)
_MARKERS = ("7–21", "7-21")
_SUPPLEMENT_MARKERS = ("7–14", "7-14")


def _candidates(model, filters, fields, supplements):
    markers = _MARKERS + (_SUPPLEMENT_MARKERS if supplements else ())
    query = Q()
    for field in fields:
        for marker in markers:
            query |= Q(**{f"{field}__contains": marker})
    return model.objects.filter(**filters).filter(query)


def plan_changes(row, fields, supplements):
    """{поле: (прежнее, новое)} для строки."""
    changes = {}
    for field in fields:
        old = getattr(row, field) or ""
        new = replace_terms(old, supplements=supplements, short=True)
        if new != old:
            changes[field] = (old, new)
    return changes


class Command(BaseCommand):
    help = "Сроки доставки в SEO лекарств и БАДов → «3–14 дней» (показ по умолчанию)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать (без него — только показ)")
        parser.add_argument("--backup", help="Файл бэкапа (jsonl), обязателен с --apply")
        parser.add_argument("--restore", help="Вернуть прежние значения из файла бэкапа")
        parser.add_argument("--show", type=int, default=10, help="Сколько примеров показать")

    def handle(self, *args, **options):
        if options["restore"]:
            return self._restore(options["restore"])
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply только с --backup <файл.jsonl>")

        backup = open(options["backup"], "a", encoding="utf-8") if options["apply"] else None
        rows_by_model, fields_by_model = Counter(), Counter()
        products = {"medicines": set(), "supplements": set()}
        examples = []
        try:
            for label, filters, fields, supplements, product_ref in TARGETS:
                model = apps.get_model(label)
                ids = list(_candidates(model, filters, fields, supplements).order_by("pk").values_list("pk", flat=True))
                for start in range(0, len(ids), BATCH_SIZE):
                    chunk = ids[start:start + BATCH_SIZE]
                    with transaction.atomic():
                        queryset = model.objects.filter(pk__in=chunk)
                        if backup:
                            queryset = queryset.select_for_update()
                        product_ids = dict(model.objects.filter(pk__in=chunk).values_list("pk", product_ref))
                        for row in queryset:
                            changes = plan_changes(row, fields, supplements)
                            if not changes:
                                continue
                            rows_by_model[label] += 1
                            fields_by_model.update(f"{label}.{field}" for field in changes)
                            if product_ids.get(row.pk):
                                products["supplements" if supplements else "medicines"].add(product_ids[row.pk])
                            if len(examples) < options["show"]:
                                field, (old, new) = next(iter(changes.items()))
                                examples.append((label, row.pk, field, old, new))
                            if backup:
                                for field, (old, new) in changes.items():
                                    backup.write(json.dumps(
                                        {"model": label, "pk": row.pk, "field": field, "old": old, "new": new},
                                        ensure_ascii=False,
                                    ) + "\n")
                                model.objects.filter(pk=row.pk).update(**{f: new for f, (_, new) in changes.items()})
        finally:
            if backup:
                backup.close()

        mode = "Записано" if options["apply"] else "Будет изменено (показ, база не менялась)"
        self.stdout.write(f"{mode}: товаров — лекарства {len(products['medicines'])}, БАДы {len(products['supplements'])}")
        for label, count in rows_by_model.items():
            self.stdout.write(f"  {label}: {count} записей")
        for key, count in sorted(fields_by_model.items()):
            self.stdout.write(f"    {key}: {count}")
        for label, pk, field, old, new in examples:
            self.stdout.write(f"\n{label} #{pk} {field}\n  было:  {old}\n  стало: {new}")

    def _restore(self, path):
        by_row = defaultdict(dict)
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    item = json.loads(line)
                    by_row[(item["model"], item["pk"])][item["field"]] = (item["old"], item["new"])
        restored = skipped = 0
        with transaction.atomic():
            for (label, pk), fields in by_row.items():
                model = apps.get_model(label)
                row = model.objects.select_for_update().filter(pk=pk).first()
                if row is None:
                    skipped += 1
                    continue
                # Поле правили после записи — не трогаем
                values = {f: old for f, (old, new) in fields.items() if (getattr(row, f) or "") == new}
                if values:
                    model.objects.filter(pk=pk).update(**values)
                    restored += 1
                else:
                    skipped += 1
        self.stdout.write(f"Возвращено записей: {restored}, пропущено: {skipped}")
