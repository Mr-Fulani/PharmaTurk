"""Уже загруженные товары SuperStep — в разделы по спросу (флиски, толстовки, термосы,
рюкзаки, угги, сабо). Показ по умолчанию; запись — ``--apply --backup``. Без сети.

Раздел считается так же, как при сборе (``SuperstepParser.subgroup_route``): по подгруппе
сайта, полу из сохранённых атрибутов, названию и бренду; первый существующий активный
раздел маршрута. Переносятся только товары, у которых этот раздел — один из новых
(``DEMAND_SLUGS``): прочие расхождения со сбором команда не трогает, а показывает.

Повторный сбор тоже переносит товар, но только когда меняется его строка списка
(``_apply_category_mapping``) — постепенно; команда переносит все сразу.

Не переносится: тип раздела другой (обувь в одежду), наценка раздела другая (цена на
сайте изменилась бы), название уже переведено и маршрут зависит от слова названия.
Пишутся ``Product`` и доменная запись через ``update()``: slug и адрес не меняются.

    manage.py move_superstep_to_demand_categories
    manage.py move_superstep_to_demand_categories --apply --backup /backups/superstep-demand-move.json
"""
import json
import re
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category, Product
from apps.catalog.utils.product_markup import get_category_markup
from apps.scrapers.parsers.superstep import SuperstepParser

DEMAND_SLUGS = frozenset({"fleece", "hoodies", "thermoses", "backpacks", "ugg-boots", "clogs"})
_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)


class Command(BaseCommand):
    help = "Переносит товары SuperStep в разделы по спросу (по умолчанию — только показ)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Перенести.")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        categories = {c.slug: c for c in Category.objects.filter(is_active=True).select_related("parent")}
        moves, skipped = [], Counter()
        products = Product.objects.filter(external_id__startswith="superstep-").select_related("category", "brand")
        for product in products.iterator():
            target, reason = self._target(product, categories)
            if reason:
                skipped[reason] += 1
            elif target is not None:
                moves.append((product, target))

        for (old, new), count in sorted(Counter((p.category.slug if p.category else "—", t.slug) for p, t in moves).items()):
            self.stdout.write(f"  {old} → {new}: {count}")
        for reason, count in skipped.most_common():
            self.stdout.write(f"  пропущено ({reason}): {count}")
        self.stdout.write(f"К переносу: {len(moves)}.")
        if not moves or not options["apply"]:
            if moves:
                self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        backup = [{"product_id": p.pk, "category_id": p.category_id, "new_category_id": t.pk} for p, t in moves]
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1)
        with transaction.atomic():
            for product, target in moves:
                Product.objects.filter(pk=product.pk).update(category=target)
                domain = product.domain_item
                if domain is not product:
                    type(domain).objects.filter(pk=domain.pk).update(category=target)
        self.stdout.write(self.style.SUCCESS(f"Перенесено: {len(moves)}. Бэкап: {options['backup']}"))

    def _target(self, product, categories):
        """(раздел, причина пропуска); (None, "") — переносить нечего."""
        attrs = (product.external_data or {}).get("attributes") or {}
        subgroup = attrs.get("superstep_subgroup") or ""
        if not subgroup and not product.name:
            return None, "нет подгруппы"
        _, route = SuperstepParser.subgroup_route(subgroup, product.name, product.brand.name if product.brand_id else "", attrs.get("gender") or "")
        slug = next((slug for slug in route if slug in categories), None)
        if slug not in DEMAND_SLUGS or (product.category and product.category.slug == slug):
            return None, ""
        if _CYRILLIC_RE.search(product.name or "") and slug in {"fleece", "ugg-boots", "clogs"}:
            return None, "название уже переведено"
        target = categories[slug]
        if product.category is None:
            return None, "нет текущего раздела"
        if target.category_type_id != product.category.category_type_id:
            return None, "другой тип раздела"
        if get_category_markup(target) != get_category_markup(product.category):
            return None, "другая наценка"
        return target, ""
