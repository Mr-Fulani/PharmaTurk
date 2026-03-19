"""Статистика рекомендательной системы."""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.catalog.models import Product
from apps.recommendations.models import RecommendationEvent, ProductVector


class Command(BaseCommand):
    help = "Статистика рекомендательной системы: покрытие векторами, CTR по алгоритмам"

    def handle(self, *args, **options):
        total_products = Product.objects.filter(is_available=True).count()
        with_vectors = ProductVector.objects.filter(is_active=True).count()
        pct = (with_vectors / total_products * 100) if total_products else 0
        self.stdout.write(
            f"Векторное покрытие: {with_vectors}/{total_products} ({pct:.1f}%)"
        )

        stats = (
            RecommendationEvent.objects.values("algorithm")
            .annotate(
                impressions=Count("id", filter=Q(event_type="impression")),
                clicks=Count("id", filter=Q(event_type="click")),
                cart_adds=Count("id", filter=Q(event_type="cart_add")),
                purchases=Count("id", filter=Q(event_type="purchase")),
            )
            .order_by("-impressions")
        )
        for stat in stats:
            imp = stat["impressions"] or 0
            clk = stat["clicks"] or 0
            pur = stat["purchases"] or 0
            ctr = (clk / imp * 100) if imp > 0 else 0
            cvr = (pur / clk * 100) if clk > 0 else 0
            self.stdout.write(f"\n{stat['algorithm']}:")
            self.stdout.write(f"  Показы: {imp}")
            self.stdout.write(f"  Клики: {clk}")
            self.stdout.write(f"  CTR: {ctr:.2f}%")
            self.stdout.write(f"  Конверсия (покупки/клики): {cvr:.2f}%")
        self.stdout.write(self.style.SUCCESS("\nDone."))
