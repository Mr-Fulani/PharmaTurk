from decimal import Decimal
from types import SimpleNamespace

from apps.catalog import pricing_serializers
from apps.catalog import serializers as catalog_serializers


def test_legacy_preferred_currency_adapter_matches_extracted_contract():
    request = SimpleNamespace(
        headers={"X-Currency": "try"},
        query_params={},
        LANGUAGE_CODE="ru",
        user=SimpleNamespace(is_authenticated=False),
    )

    assert catalog_serializers._preferred_currency(request) == "TRY"
    assert pricing_serializers.preferred_currency(request) == "TRY"


def test_legacy_markup_adapter_preserves_existing_monkeypatch_point(monkeypatch):
    monkeypatch.setattr(
        catalog_serializers,
        "_effective_product_markup",
        lambda product: (Decimal("10"), "contract-test"),
    )
    payload = {
        "price": Decimal("100"),
        "price_formatted": "100 TRY",
        "variants": [
            {
                "price": Decimal("50"),
                "price_formatted": "50 TRY",
            }
        ],
    }

    result = catalog_serializers._apply_product_markup_to_payload(
        payload,
        SimpleNamespace(),
    )

    assert result["price"] == Decimal("110.00")
    assert result["price_formatted"] == "110.00 TRY"
    assert result["variants"][0]["price"] == Decimal("55.00")
    assert result["variants"][0]["price_formatted"] == "55.00 TRY"
    assert result["product_markup_percent"] == Decimal("10")
    assert result["product_markup_source"] == "contract-test"


def test_extracted_markup_contract_covers_nested_price_shapes():
    payload = {
        "current_price": {"amount": Decimal("10"), "currency": "USD"},
        "prices_in_currencies": {
            "USD": {"price_with_margin": Decimal("20")},
        },
        "prices_info": {
            "rub_price_with_margin": Decimal("30"),
        },
    }

    result = pricing_serializers.apply_product_markup_to_payload(
        payload,
        SimpleNamespace(),
        markup_resolver=lambda product: (Decimal("25"), "brand"),
    )

    assert result["current_price"] == {
        "amount": Decimal("12.50"),
        "currency": "USD",
        "formatted": "12.50 USD",
    }
    assert result["prices_in_currencies"]["USD"]["price_with_margin"] == Decimal("25.00")
    assert result["prices_info"]["rub_price_with_margin"] == Decimal("37.50")
    assert result["product_markup_source"] == "brand"
