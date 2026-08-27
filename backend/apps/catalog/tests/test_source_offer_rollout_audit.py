import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.services import source_offer_rollout_audit
from apps.catalog.services.source_offer_rollout_audit import (
    build_source_offer_rollout_report,
)


@pytest.fixture
def source_product(db):
    return Product.objects.create(
        name="Rollout product",
        slug="rollout-product",
        price="199.90",
        currency="RUB",
        external_url="https://www.zara.com/tr/rollout-product",
        external_data={"source": "zara"},
        stock_quantity=1000,
    )


def _offer(product, *, checked_at):
    return ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        source_domain="www.zara.com",
        canonical_url=product.external_url,
        source_price="199.90",
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
        last_checked_at=checked_at,
        last_successful_check_at=checked_at,
    )


@pytest.mark.django_db
def test_rollout_audit_reports_coverage_without_mutating_data(source_product):
    now = timezone.now()
    _offer(source_product, checked_at=now - timedelta(seconds=30))
    before = {
        "products": Product.objects.count(),
        "offers": ProductSourceOffer.objects.count(),
    }

    report = build_source_offer_rollout_report(
        now=now,
        stale_seconds=60,
    )

    assert report["mode"] == "READ_ONLY"
    assert report["schema"]["all_required_migrations_applied"] is True
    assert report["catalog"]["source_candidate_products"] == 1
    assert report["catalog"]["candidate_products_with_active_offers"] == 1
    assert report["catalog"]["coverage_percent"] == 100.0
    assert report["catalog"]["legacy_fake_stock_candidates"] == {"1000": 1}
    assert report["offers"]["stale"] == 0
    assert report["offers"]["per_source"] == [
        {
            "parser_key": "zara",
            "offers": 1,
            "products": 1,
            "never_checked": 0,
            "stale": 0,
            "with_errors": 0,
        }
    ]
    assert report["ready_for_source_rollout"] is True
    assert {
        "products": Product.objects.count(),
        "offers": ProductSourceOffer.objects.count(),
    } == before


@pytest.mark.django_db
def test_rollout_audit_skips_tables_whose_migrations_are_missing(source_product, monkeypatch):
    monkeypatch.setattr(
        source_offer_rollout_audit,
        "_applied_migrations",
        lambda **_kwargs: {("catalog", "0202_productsourceoffer")},
    )

    report = build_source_offer_rollout_report()

    assert report["cart"] == {
        "available": False,
        "reason": "migration_0010_not_applied",
    }
    assert report["orders"] == {
        "available": False,
        "reason": "migration_0011_not_applied",
    }
    assert "missing_migration:orders.0010_cartitem_source_verification" in report["blockers"]
    assert report["ready_for_source_rollout"] is False


@pytest.mark.django_db
def test_rollout_audit_json_command_is_machine_readable(source_product):
    _offer(source_product, checked_at=timezone.now())
    stdout = StringIO()

    call_command("audit_source_offer_rollout", format="json", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["mode"] == "READ_ONLY"
    assert report["offers"]["per_source"][0]["parser_key"] == "zara"
    assert report["feature_flags"]["verification_enabled"] is False
