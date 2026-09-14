"""Read-only category proposals; deliberately no --apply mode or seed invocation."""

from collections import Counter, defaultdict
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.medicine_taxonomy import (
    MEDICINES_SUBCATEGORIES,
    MEDICINE_TAXONOMY_VERSION,
    propose_medicine_category,
)
from apps.catalog.models import Category, MedicineProduct


class Command(BaseCommand):
    help = "Предложить категории медикаментов без записи в базу и без запуска парсера"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--examples", type=int, default=3, help="Примеров на категорию/причину (0–10)")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        limit = options.get("limit")
        examples = options.get("examples", 3)
        if limit is not None and limit < 1:
            raise CommandError("--limit должен быть положительным")
        if not 0 <= examples <= 10:
            raise CommandError("--examples должен быть от 0 до 10")
        # PostgreSQL itself rejects writes, including accidentally introduced ones.
        # A consistent snapshot is needed while the regular parser keeps running.
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            report = self._preview(limit=limit, example_limit=examples)
        if options.get("as_json"):
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        self.stdout.write(f"DRY RUN / {report['taxonomy_version']} — изменений в БД: 0")
        self.stdout.write(f"Проверено: {report['total']}; статусы: {report['statuses']}")
        for category in report["categories"]:
            self.stdout.write(f"  {category['name']}: {category['proposed']}")
        self.stdout.write(f"Причины проверки/пропуска: {report['reasons']}")
        self.stdout.write("Для примеров и наличия категорий в БД используйте --json.")

    def _preview(self, *, limit, example_limit):
        catalog = {
            row["slug"]: row for row in Category.objects.filter(
                slug__in=[item[2] for item in MEDICINES_SUBCATEGORIES]
            ).values("slug", "is_active", "parent__slug")
        }
        queryset = MedicineProduct.objects.order_by("id").values(
            "id", "base_product_id", "name", "is_active", "category__slug",
            "atc_code", "barcode", "external_data__attributes__atc_code",
            "external_data__attributes__barcode", "external_data__is_stub",
            "external_data__attributes__is_stub",
        )
        if limit is not None:
            queryset = queryset[:limit]
        statuses, reasons, distribution = Counter(), Counter(), Counter()
        samples = defaultdict(list)
        total = 0
        for row in queryset.iterator(chunk_size=500):
            total += 1
            proposal = propose_medicine_category(
                atc_code=row["atc_code"],
                source_atc_code=row["external_data__attributes__atc_code"],
                barcode=row["barcode"],
                source_barcode=row["external_data__attributes__barcode"],
                is_stub=(row["external_data__is_stub"] is True
                         or row["external_data__attributes__is_stub"] is True),
                current_category_slug=row["category__slug"],
            )
            statuses[proposal.status] += 1
            reasons[proposal.reason] += 1
            if proposal.status == "proposed":
                distribution[proposal.category_slug] += 1
            sample_key = proposal.category_slug if proposal.status == "proposed" else proposal.reason
            if len(samples[sample_key]) < example_limit:
                samples[sample_key].append({
                    "medicine_id": row["id"], "product_id": row["base_product_id"],
                    "name": row["name"], "current_category": row["category__slug"],
                    "suggested_category": proposal.category_slug,
                    "atc": row["atc_code"], "source_atc": row["external_data__attributes__atc_code"],
                    "status": proposal.status, "reason": proposal.reason,
                })
        return {
            "mode": "dry_run", "writes": 0,
            "database_read_only": connection.vendor == "postgresql",
            "taxonomy_version": MEDICINE_TAXONOMY_VERSION,
            "generated_at": timezone.now().isoformat(), "total": total,
            "statuses": dict(statuses), "reasons": dict(reasons),
            "categories": [{
                "slug": item[2], "name": item[0], "proposed": distribution[item[2]],
                "ready_in_database": bool(
                    catalog.get(item[2], {}).get("is_active")
                    and catalog[item[2]]["parent__slug"] == "medicines"
                ),
            } for item in MEDICINES_SUBCATEGORIES],
            "examples": dict(samples),
        }
