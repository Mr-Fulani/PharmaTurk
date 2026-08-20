"""Report CoinRemitter/local payment drift without changing payment state."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.payments.models import CryptoPayment, CryptoPaymentStatus
from apps.payments.providers.coinremitter import get_invoice
from apps.payments.reconciliation import classify_coinremitter_state


class Command(BaseCommand):
    help = (
        "Read-only reconciliation of local CryptoPayment rows against the "
        "authenticated CoinRemitter invoice/get API. This command never writes statuses."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum provider API calls (default: 100, maximum: 1000).",
        )
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=5,
            help="Ignore freshly created invoices (default: 5 minutes).",
        )
        parser.add_argument(
            "--all-statuses",
            action="store_true",
            help="Check pending, confirmed and expired rows; default checks pending only.",
        )
        parser.add_argument(
            "--show-consistent",
            action="store_true",
            help="Print consistent rows in addition to drift/error rows.",
        )
        parser.add_argument(
            "--fail-on-drift",
            action="store_true",
            help="Exit non-zero when drift or provider lookup failures are found.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        older_than_minutes = options["older_than_minutes"]
        if limit < 1 or limit > 1000:
            raise CommandError("--limit must be between 1 and 1000.")
        if older_than_minutes < 0 or older_than_minutes > 43_200:
            raise CommandError("--older-than-minutes must be between 0 and 43200.")

        statuses = [CryptoPaymentStatus.PENDING]
        if options["all_statuses"]:
            statuses = list(CryptoPaymentStatus.values)

        cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
        payments = list(
            CryptoPayment.objects.select_related("order")
            .filter(
                provider="coinremitter",
                status__in=statuses,
                created_at__lte=cutoff,
            )
            .order_by("created_at", "pk")[:limit]
        )

        counts: Counter[str] = Counter()
        drift_count = 0
        critical_count = 0
        unavailable_count = 0

        for payment in payments:
            provider_invoice = get_invoice(payment.invoice_code or payment.invoice_id)
            if provider_invoice is None:
                category = "provider_unavailable"
                counts[category] += 1
                unavailable_count += 1
                self.stderr.write(
                    f"payment={payment.pk} order={payment.order.number} "
                    f"category={category}"
                )
                continue

            result = classify_coinremitter_state(payment, provider_invoice)
            counts[result.category] += 1
            if result.is_drift:
                drift_count += 1
            if result.is_critical:
                critical_count += 1
            if result.is_drift or options["show_consistent"]:
                self.stdout.write(
                    f"payment={payment.pk} order={payment.order.number} "
                    f"provider_status={result.provider_status_code} "
                    f"category={result.category}"
                )

        categories = ",".join(
            f"{name}:{count}" for name, count in sorted(counts.items())
        ) or "none"
        self.stdout.write(
            f"checked={len(payments)} drift={drift_count} critical={critical_count} "
            f"unavailable={unavailable_count} categories={categories}"
        )
        self.stdout.write(
            self.style.WARNING(
                "READ ONLY: no local or provider payment state was changed. "
                "Use the authenticated webhook/reconciliation runbook for remediation."
            )
        )

        if options["fail_on_drift"] and (drift_count or unavailable_count):
            raise CommandError(
                "CoinRemitter reconciliation found drift or unavailable provider lookups."
            )
