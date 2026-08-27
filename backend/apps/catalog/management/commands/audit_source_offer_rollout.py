"""Print a read-only source-offer rollout readiness report."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.source_offer_rollout_audit import (
    build_source_offer_rollout_report,
)


class Command(BaseCommand):
    help = (
        "Read-only rollout audit for source-offer migrations, coverage, freshness, "
        "feature flags and cart/order readiness."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=("text", "json"),
            default="text",
            help="Формат отчёта (по умолчанию text).",
        )
        parser.add_argument(
            "--stale-seconds",
            type=int,
            default=None,
            help="Переопределить freshness threshold только для отчёта.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Вернуть ненулевой exit code при rollout blockers.",
        )

    def handle(self, *args, **options):
        stale_seconds = options["stale_seconds"]
        if stale_seconds is not None and not 1 <= stale_seconds <= 604800:
            raise CommandError("--stale-seconds должен быть от 1 до 604800")

        report = build_source_offer_rollout_report(stale_seconds=stale_seconds)
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            self._write_text(report)

        if options["fail_on_blockers"] and report["blockers"]:
            raise CommandError(
                "Source-offer rollout заблокирован: " + ", ".join(report["blockers"])
            )

    def _write_text(self, report):
        schema = report["schema"]
        catalog = report["catalog"]
        offers = report["offers"]
        self.stdout.write(
            f"mode={report['mode']} generated_at={report['generated_at']} "
            f"database_alias={report['database_alias']}"
        )
        self.stdout.write(
            "schema_all_applied=" + str(schema["all_required_migrations_applied"]).lower()
        )
        for migration, is_applied in schema["migrations"].items():
            self.stdout.write(f"migration {migration} applied={str(is_applied).lower()}")
        self.stdout.write(
            "catalog "
            f"products={catalog['products_total']} "
            f"candidates={catalog['source_candidate_products']} "
            f"covered={catalog['candidate_products_with_active_offers']} "
            f"coverage_percent={catalog['coverage_percent']} "
            f"fake_stock={catalog['legacy_fake_stock_candidates']}"
        )
        self.stdout.write(
            "offers "
            f"total={offers['total']} active={offers['active']} "
            f"inactive={offers['inactive']} never_checked={offers['never_checked']} "
            f"stale={offers['stale']}"
        )
        for source in offers["per_source"]:
            self.stdout.write(
                "source "
                f"parser={source['parser_key']} offers={source['offers']} "
                f"products={source['products']} stale={source['stale']} "
                f"never_checked={source['never_checked']} "
                f"with_errors={source['with_errors']}"
            )
        self.stdout.write(f"cart {report['cart']}")
        self.stdout.write(f"orders {report['orders']}")
        self.stdout.write(f"feature_flags {report['feature_flags']}")
        self.stdout.write(f"blockers {report['blockers']}")
        self.stdout.write(f"warnings {report['warnings']}")
        self.stdout.write(
            "ready_for_source_rollout=" + str(report["ready_for_source_rollout"]).lower()
        )
