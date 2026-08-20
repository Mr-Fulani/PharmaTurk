"""DB-free regression tests for CoinRemitter frontend redirect locales."""

from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings

from apps.orders.views import _create_crypto_invoice


def _invoice(invoice_id: str) -> dict:
    """Return the minimal successful provider payload consumed by the view."""
    return {
        "invoice_id": invoice_id,
        "address": "T-test-address",
        "amount": "10",
        "amount_usd": "10",
    }


@override_settings(
    SITE_URL="https://api.example.com",
    FRONTEND_SITE_URL="https://shop.example.com",
    CRYPTO_DUMMY_MODE=False,
)
def test_crypto_redirect_uses_unprefixed_default_russian_locale():
    with patch(
        "apps.payments.providers.coinremitter.create_invoice",
        return_value=_invoice("invoice-1"),
    ) as create_invoice:
        invoice, _ = _create_crypto_invoice("ORDER1", Decimal("10"), "USD", "ru")

    assert invoice["invoice_id"] == "invoice-1"
    kwargs = create_invoice.call_args.kwargs
    assert kwargs["success_url"] == "https://shop.example.com/checkout-success?number=ORDER1&locale=ru"
    assert kwargs["fail_url"] == "https://shop.example.com/checkout-crypto?number=ORDER1&locale=ru"


@override_settings(
    SITE_URL="https://api.example.com",
    FRONTEND_SITE_URL="https://shop.example.com",
    CRYPTO_DUMMY_MODE=False,
)
def test_crypto_redirect_prefixes_english_locale():
    with patch(
        "apps.payments.providers.coinremitter.create_invoice",
        return_value=_invoice("invoice-2"),
    ) as create_invoice:
        _create_crypto_invoice("ORDER2", Decimal("10"), "USD", "en")

    kwargs = create_invoice.call_args.kwargs
    assert kwargs["success_url"] == "https://shop.example.com/en/checkout-success?number=ORDER2&locale=en"
    assert kwargs["fail_url"] == "https://shop.example.com/en/checkout-crypto?number=ORDER2&locale=en"
