"""Conservative, bounded rollout command for supplement market offers."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Category, SupplementProduct
from apps.catalog.services.supplement_stock_discovery import (
    SupplementStockDiscoveryError,
    SupplementStockDiscoveryService,
)
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.akakce import AkakceParser


class Command(BaseCommand):
    help = (
        "Demand-driven Akakce matching for supplements. Dry-run by default; "
        "only strong title/dosage matches may create ProductSourceOffer rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Сохранить найденные offers")
        parser.add_argument(
            "--create-config",
            action="store_true",
            help="Создать proxy-enabled ScraperConfig Akakce (только вместе с --apply)",
        )
        parser.add_argument("--supplement-id", type=int, action="append", default=[])
        parser.add_argument("--slug", action="append", default=[])
        parser.add_argument("--limit", type=int, default=10)

    @staticmethod
    def _existing_config() -> ScraperConfig | None:
        return (
            ScraperConfig.objects.filter(
                parser_class__iexact="akakce",
                is_enabled=True,
                status="active",
                use_proxy=True,
            )
            .order_by("priority", "pk")
            .first()
        )

    def _ensure_config(self, queryset) -> ScraperConfig:
        config = self._existing_config()
        if config is not None:
            return config

        category = Category.objects.filter(slug="supplements").order_by("pk").first()
        if category is None:
            category = (
                queryset.exclude(category_id=None)
                .values_list("category_id", flat=True)
                .first()
            )
            category = Category.objects.filter(pk=category).first() if category else None
        if category is None:
            raise CommandError("Не найдена категория для ScraperConfig Akakce")

        config, _ = ScraperConfig.objects.get_or_create(
            name="akakce-supplement-stock",
            defaults={
                "parser_class": "akakce",
                "base_url": "https://www.akakce.com",
                "description": "Demand-driven supplement market availability adapter",
                "default_category": category,
                "status": "active",
                "is_enabled": True,
                "priority": 20,
                "delay_min": 1,
                "delay_max": 2,
                "timeout": 15,
                "max_retries": 1,
                "sync_enabled": False,
                "ai_on_create_enabled": False,
                "ai_on_update_enabled": False,
                "use_proxy": True,
                "user_agent": AkakceParser.FIXED_USER_AGENT,
            },
        )
        if (
            str(config.parser_class or "").casefold() != "akakce"
            or not config.is_enabled
            or config.status != "active"
            or not config.use_proxy
        ):
            raise CommandError(
                "ScraperConfig akakce-supplement-stock существует, но не является "
                "активной proxy-enabled конфигурацией Akakce"
            )
        return config

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        create_config = bool(options["create_config"])
        limit = int(options["limit"] or 0)
        if create_config and not apply_changes:
            raise CommandError("--create-config требует --apply")
        if not 1 <= limit <= 100:
            raise CommandError("--limit должен быть от 1 до 100")

        queryset = (
            SupplementProduct.objects.filter(is_active=True, base_product__isnull=False)
            .select_related("base_product", "category")
            .order_by("pk")
        )
        ids = [value for value in options["supplement_id"] if value > 0]
        slugs = [str(value or "").strip() for value in options["slug"] if str(value or "").strip()]
        if ids:
            queryset = queryset.filter(pk__in=ids)
        if slugs:
            queryset = queryset.filter(slug__in=slugs)

        if create_config:
            config = self._ensure_config(queryset)
            self.stdout.write(f"ScraperConfig готов: id={config.pk} name={config.name}")
        elif self._existing_config() is None:
            raise CommandError(
                "Нет активного proxy-enabled ScraperConfig Akakce. "
                "Используйте --apply --create-config для первого canary."
            )

        queryset = queryset[:limit]
        service = SupplementStockDiscoveryService()
        counters: dict[str, int] = {}
        for supplement in queryset:
            try:
                result = service.discover(
                    supplement,
                    persist=apply_changes,
                    force=True,
                )
                status = result.status
                detail = (
                    f" candidate={result.candidate_name!r} confidence={result.confidence}"
                    if result.candidate_name
                    else ""
                )
                if result.offer is not None:
                    detail += f" offer_id={result.offer.pk}"
            except SupplementStockDiscoveryError as exc:
                status = f"error:{exc.code}"
                detail = f" retryable={str(exc.retryable).lower()}"
            counters[status] = counters.get(status, 0) + 1
            self.stdout.write(
                f"supplement_id={supplement.pk} base_product_id={supplement.base_product_id} "
                f"status={status}{detail}"
            )

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(f"{mode}: {counters}")
