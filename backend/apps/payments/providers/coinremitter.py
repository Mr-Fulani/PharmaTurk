"""CoinRemitter API provider for USDT (TRC20/ERC20) invoices."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

COINREMITTER_BASE = "https://api.coinremitter.com/v1"


def _get_config() -> dict[str, str]:
    """Read CoinRemitter config from environment/settings."""
    return {
        "api_key": getattr(settings, "COINREMITTER_API_KEY", "") or "",
        "api_password": getattr(settings, "COINREMITTER_API_PASSWORD", "") or "",
        "coin": getattr(settings, "COINREMITTER_COIN", "USDTTRC20") or "USDTTRC20",
    }


def _get_invoice(config: dict[str, str], invoice_id: str) -> dict | None:
    """Fetch full invoice details via invoice/get. Returns data dict or None."""
    url = f"{COINREMITTER_BASE}/invoice/get"
    try:
        resp = requests.post(
            url,
            data={"invoice_id": invoice_id},
            headers={
                "x-api-key": config["api_key"],
                "x-api-password": config["api_password"],
                "Accept": "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("success") and data.get("data"):
            return data["data"]
        logger.warning("CoinRemitter invoice/get failed: %s", data)
    except requests.RequestException as e:
        logger.warning("CoinRemitter invoice/get request failed: %s", e)
    return None


def create_invoice(
    amount_fiat: Decimal | float,
    fiat_currency: str,
    order_number: str,
    notify_url: str,
    success_url: str = "",
    fail_url: str = "",
    expiry_minutes: int = 30,
    description: str = "",
) -> dict[str, Any] | None:
    """
    Create a CoinRemitter invoice for the given amount.

    Returns dict with: invoice_id, address, qr_code, amount (crypto), amount_usd, expires_at, invoice_url.
    Returns None on API error.
    """
    config = _get_config()
    if not config["api_key"] or not config["api_password"]:
        logger.warning("CoinRemitter: API key or password not set")
        return None

    # Coin is determined by wallet (API key). Path is /v1/invoice/create per Swagger/Node SDK.
    url = f"{COINREMITTER_BASE}/invoice/create"

    # CoinRemitter проверяет success_url/fail_url/notify_url POST-запросом — нужен публичный URL.
    # localhost недоступен с их серверов → не передаём, инвойс создаётся без редиректа после оплаты.
    def _is_public(u: str) -> bool:
        return bool(u and "localhost" not in u.lower() and "127.0.0.1" not in u)

    payload: dict[str, str | int] = {
        "amount": str(amount_fiat),
        "fiat_currency": fiat_currency.upper()[:3],
        "custom_data1": order_number[:30],
        "expiry_time_in_minutes": str(expiry_minutes),
    }
    if _is_public(notify_url):
        payload["notify_url"] = notify_url
    if _is_public(success_url):
        payload["success_url"] = success_url
    if _is_public(fail_url):
        payload["fail_url"] = fail_url
    if description:
        payload["description"] = description[:255]

    headers = {
        "x-api-key": config["api_key"],
        "x-api-password": config["api_password"],
        "Accept": "application/json",
    }

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=30)
        data = resp.json()
    except requests.RequestException as e:
        logger.exception("CoinRemitter create_invoice request failed: %s", e)
        return None

    if not data.get("success"):
        logger.warning(
            "CoinRemitter create_invoice failed: %s (sent amount=%s %s)",
            data, amount_fiat, fiat_currency,
        )
        return None

    inner = data.get("data") or {}
    invoice_id_short = inner.get("invoice_id") or ""
    invoice_id_long = inner.get("id") or ""

    # Create response may not include address/qr_code. Fetch full invoice via invoice/get.
    address = ""
    qr_code = ""
    if invoice_id_short or invoice_id_long:
        get_data = _get_invoice(config, invoice_id_short or invoice_id_long)
        if get_data:
            inner = get_data
            logger.info("CoinRemitter: got address/qr from invoice/get")

    # Parse address and qr_code from response (create or get)
    if "crypto_currency" in inner:
        cc = inner["crypto_currency"]
        if isinstance(cc, list) and cc:
            first = cc[0]
            address = first.get("address") or first.get("wallet_address") or ""
            qr_code = first.get("qr_code") or first.get("qr_code_url") or ""
        elif isinstance(cc, dict):
            address = cc.get("address") or cc.get("wallet_address") or ""
            qr_code = cc.get("qr_code") or cc.get("qr_code_url") or ""
    if not address:
        address = inner.get("address") or inner.get("wallet_address") or ""
    if not qr_code:
        qr_code = inner.get("qr_code") or inner.get("qr_code_url") or ""

    amount_str = inner.get("amount") or "0"
    usd_str = inner.get("usd_amount") or amount_str
    try:
        amount_crypto = Decimal(amount_str)
        amount_usd = Decimal(usd_str)
    except Exception:
        amount_crypto = Decimal("0")
        amount_usd = Decimal(usd_str) if isinstance(amount_fiat, Decimal) else Decimal(str(amount_fiat))

    from datetime import datetime, timedelta, timezone
    from django.utils import timezone as django_tz
    expires_at = None
    if "expire_on_timestamp" in inner:
        try:
            ts = int(inner["expire_on_timestamp"])
            expires_at = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError):
            pass
    if expires_at is None:
        expires_at = django_tz.now() + timedelta(minutes=expiry_minutes)

    return {
        "invoice_id": inner.get("id") or inner.get("invoice_id") or "",
        "address": address,
        "qr_code": qr_code,
        "amount": amount_crypto,
        "amount_usd": amount_usd,
        "currency": fiat_currency.upper()[:3],
        "expires_at": expires_at,
        "invoice_url": inner.get("url") or "",
    }
