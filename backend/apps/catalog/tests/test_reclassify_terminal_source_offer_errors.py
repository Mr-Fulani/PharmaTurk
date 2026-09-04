from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer


def _offer(*, parser_key: str, variant_key: str, size_key: str, message: str):
    product = Product.objects.create(
        name=f"Terminal {parser_key} {variant_key} {size_key}",
        slug=f"terminal-{parser_key}-{variant_key}-{size_key}".lower(),
        product_type="clothing",
    )
    checked_at = timezone.now()
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key=parser_key,
        canonical_url=f"https://www.{parser_key}.com/product-1",
        external_product_id=f"{parser_key}-product-1",
        external_sku=f"{parser_key}-sku-1",
        variant_key=variant_key,
        size_key=size_key,
        selected_options={"size": size_key},
        availability_status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.UNKNOWN,
        last_checked_at=checked_at,
        last_error_code="option_not_found",
        last_error_message=message,
    )
    return offer, checked_at


@pytest.mark.django_db
def test_command_is_dry_run_by_default_and_requires_exact_source_mapping():
    eligible, _ = _offer(
        parser_key="lcw",
        variant_key="lcw-var-1",
        size_key="125",
        message="Source option was not found: 125",
    )
    lookalike, _ = _offer(
        parser_key="lcw",
        variant_key="lcw-var-2",
        size_key="115",
        message="Source option was not found: lcw-var-2",
    )
    stdout = StringIO()

    call_command("reclassify_terminal_source_offer_errors", stdout=stdout)

    eligible.refresh_from_db()
    lookalike.refresh_from_db()
    assert eligible.last_error_code == "option_not_found"
    assert lookalike.last_error_code == "option_not_found"
    assert "mode=DRY-RUN eligible=1 skipped=1" in stdout.getvalue()


@pytest.mark.django_db
def test_command_applies_only_lcw_size_and_zara_variant_terminal_outcomes():
    lcw, lcw_checked_at = _offer(
        parser_key="lcw",
        variant_key="lcw-var-1",
        size_key="Standart",
        message="Source option was not found: Standart",
    )
    zara, zara_checked_at = _offer(
        parser_key="zara",
        variant_key="zara-variant-9",
        size_key="M",
        message="Source option was not found: zara-variant-9",
    )
    stdout = StringIO()

    call_command(
        "reclassify_terminal_source_offer_errors",
        "--apply",
        stdout=stdout,
    )

    lcw.refresh_from_db()
    zara.refresh_from_db()
    assert lcw.availability_status == ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
    assert zara.availability_status == ProductSourceOffer.AvailabilityStatus.DISCONTINUED
    for offer, checked_at in ((lcw, lcw_checked_at), (zara, zara_checked_at)):
        assert offer.stock_precision == ProductSourceOffer.StockPrecision.BOOLEAN
        assert offer.stock_quantity is None
        assert offer.last_successful_check_at == checked_at
        assert offer.last_error_code == ""
        assert offer.last_error_message == ""
    assert "mode=APPLY eligible=2 skipped=0" in stdout.getvalue()
