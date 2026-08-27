"""Typed, read-only contract for checking one supplier offer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx
import requests

from apps.http_errors import ExternalAccessBlockedError


class OfferAvailability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LIMITED = "limited"
    DISCONTINUED = "discontinued"
    UNKNOWN = "unknown"
    SOURCE_UNREACHABLE = "source_unreachable"
    UNSUPPORTED = "unsupported"


class OfferStockPrecision(StrEnum):
    EXACT = "exact"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


class OfferCheckErrorCode(StrEnum):
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    NOT_FOUND = "not_found"
    GONE = "gone"
    OPTION_NOT_FOUND = "option_not_found"
    TIMEOUT = "timeout"
    ACCESS_BLOCKED = "access_blocked"
    TRANSPORT_ERROR = "transport_error"
    MALFORMED_RESPONSE = "malformed_response"
    INVALID_SOURCE = "invalid_source"
    CIRCUIT_OPEN = "circuit_open"
    RATE_LIMITED = "rate_limited"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class OfferCheckError:
    code: OfferCheckErrorCode
    message: str
    retryable: bool
    http_status: int | None = None


@dataclass(frozen=True)
class OfferCheckContext:
    canonical_url: str
    external_product_id: str = ""
    external_sku: str = ""
    variant_key: str = ""
    size_key: str = ""
    selected_options: dict[str, Any] = field(default_factory=dict)
    parser_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OfferCheckResult:
    availability_status: OfferAvailability
    stock_precision: OfferStockPrecision
    canonical_url: str
    source_price: Decimal | None = None
    source_currency: str = ""
    stock_quantity: int | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: OfferCheckError | None = None
    response_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.stock_precision == OfferStockPrecision.EXACT and self.stock_quantity is None:
            raise ValueError("exact stock requires stock_quantity")
        if self.stock_precision != OfferStockPrecision.EXACT and self.stock_quantity is not None:
            raise ValueError("non-exact stock must not expose stock_quantity")
        if self.stock_quantity is not None and self.stock_quantity < 0:
            raise ValueError("stock_quantity must be non-negative")

    @property
    def is_success(self) -> bool:
        return self.error is None


class OfferVerificationError(RuntimeError):
    def __init__(
        self,
        code: OfferCheckErrorCode,
        message: str,
        *,
        retryable: bool,
        http_status: int | None = None,
    ):
        self.error = OfferCheckError(
            code=code,
            message=message,
            retryable=retryable,
            http_status=http_status,
        )
        super().__init__(message)


class UnsupportedOfferVerification(OfferVerificationError):
    def __init__(self, parser_key: str):
        super().__init__(
            OfferCheckErrorCode.UNSUPPORTED,
            f"Parser '{parser_key}' does not support live offer verification",
            retryable=False,
        )


class OfferNotFound(OfferVerificationError):
    def __init__(self, canonical_url: str):
        super().__init__(
            OfferCheckErrorCode.NOT_FOUND,
            f"Source offer was not found: {canonical_url}",
            retryable=False,
            http_status=404,
        )


class OfferOptionNotFound(OfferVerificationError):
    def __init__(self, option: str):
        super().__init__(
            OfferCheckErrorCode.OPTION_NOT_FOUND,
            f"Source option was not found: {option}",
            retryable=False,
        )


class OfferGone(OfferVerificationError):
    def __init__(self, canonical_url: str):
        super().__init__(
            OfferCheckErrorCode.GONE,
            f"Source offer is permanently gone: {canonical_url}",
            retryable=False,
            http_status=410,
        )


class MalformedOfferResponse(OfferVerificationError):
    def __init__(self, message: str = "Source response does not contain offer data"):
        super().__init__(
            OfferCheckErrorCode.MALFORMED_RESPONSE,
            message,
            retryable=False,
        )


class OfferSourceUnavailable(OfferVerificationError):
    pass


_F = TypeVar("_F", bound=Callable[..., OfferCheckResult])


def translate_offer_check_errors(func: _F) -> _F:
    """Translate known transport failures without hiding parser programming errors."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OfferVerificationError:
            raise
        except ExternalAccessBlockedError as exc:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.ACCESS_BLOCKED,
                str(exc),
                retryable=True,
                http_status=exc.status_code or 403,
            ) from exc
        except (httpx.TimeoutException, requests.Timeout, TimeoutError) as exc:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TIMEOUT,
                str(exc) or "Supplier request timed out",
                retryable=True,
            ) from exc
        except (httpx.HTTPStatusError, requests.HTTPError) as exc:
            response = getattr(exc, "response", None)
            status_code = int(getattr(response, "status_code", 0) or 0)
            request = getattr(exc, "request", None) or getattr(response, "request", None)
            url = str(getattr(request, "url", "") or "")
            if status_code == 404:
                raise OfferNotFound(url) from exc
            if status_code == 410:
                raise OfferGone(url) from exc
            if status_code in {401, 403, 407}:
                raise OfferSourceUnavailable(
                    OfferCheckErrorCode.ACCESS_BLOCKED,
                    str(exc),
                    retryable=True,
                    http_status=status_code,
                ) from exc
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                str(exc) or f"Supplier returned HTTP {status_code}",
                retryable=status_code == 429 or status_code >= 500,
                http_status=status_code or None,
            ) from exc
        except (httpx.RequestError, requests.RequestException) as exc:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                str(exc) or "Supplier transport error",
                retryable=True,
            ) from exc

    return wrapper  # type: ignore[return-value]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _same(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _select_variant(context: OfferCheckContext, variants: list[dict[str, Any]]) -> dict[str, Any]:
    if not variants:
        if context.variant_key:
            raise OfferOptionNotFound(context.variant_key)
        return {}

    if context.variant_key:
        for variant in variants:
            if _same(variant.get("external_id"), context.variant_key):
                return variant
        raise OfferOptionNotFound(context.variant_key)

    if context.external_sku:
        for variant in variants:
            if _same(variant.get("sku"), context.external_sku):
                return variant

    selected_color = context.selected_options.get("color")
    if selected_color:
        for variant in variants:
            if _same(variant.get("color"), selected_color):
                return variant

    return variants[0]


def _select_size(context: OfferCheckContext, sizes: list[dict[str, Any]]) -> dict[str, Any]:
    if not context.size_key:
        return {}
    for size in sizes:
        if _same(size.get("size"), context.size_key):
            return size
    raise OfferOptionNotFound(context.size_key)


def result_from_scraped_product(
    context: OfferCheckContext,
    scraped_product: Any,
    *,
    exact_stock: bool = False,
) -> OfferCheckResult:
    """Select the requested option from a read-only ScrapedProduct payload."""
    if scraped_product is None:
        raise OfferNotFound(context.canonical_url)
    if isinstance(scraped_product, list):
        candidates = [row for row in scraped_product if row is not None]
        if context.external_product_id:
            scraped_product = next(
                (
                    row
                    for row in candidates
                    if _same(getattr(row, "external_id", ""), context.external_product_id)
                ),
                None,
            )
        else:
            scraped_product = candidates[0] if candidates else None
        if scraped_product is None:
            raise OfferNotFound(context.canonical_url)

    attributes = getattr(scraped_product, "attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    raw_variants = attributes.get("fashion_variants") or attributes.get("furniture_variants") or []
    variants = [row for row in raw_variants if isinstance(row, dict)]
    variant = _select_variant(context, variants)
    sizes = [row for row in variant.get("sizes", []) if isinstance(row, dict)] if variant else []
    size = _select_size(context, sizes)

    observed = size or variant
    is_available = observed.get("is_available") if observed else None
    if is_available is None:
        is_available = getattr(scraped_product, "is_available", False)
    raw_quantity = observed.get("stock_quantity") if observed else None
    if raw_quantity is None and not variant:
        raw_quantity = getattr(scraped_product, "stock_quantity", None)

    quantity = None
    precision = OfferStockPrecision.BOOLEAN
    if exact_stock and raw_quantity is not None:
        try:
            quantity = max(int(raw_quantity), 0)
        except (TypeError, ValueError):
            quantity = None
        if quantity is not None:
            precision = OfferStockPrecision.EXACT

    raw_availability = str(observed.get("availability") if observed else "").strip().casefold()
    if precision == OfferStockPrecision.EXACT:
        availability = (
            OfferAvailability.IN_STOCK
            if quantity and quantity > 0
            else OfferAvailability.OUT_OF_STOCK
        )
    elif raw_availability in {"low_on_stock", "low_stock", "limited"}:
        availability = OfferAvailability.LIMITED
    else:
        availability = (
            OfferAvailability.IN_STOCK if bool(is_available) else OfferAvailability.OUT_OF_STOCK
        )

    price_value = variant.get("price") if variant.get("price") is not None else None
    if price_value is None:
        price_value = getattr(scraped_product, "price", None)
    currency = (
        str(variant.get("currency") or getattr(scraped_product, "currency", "") or "")
        .strip()
        .upper()
    )
    canonical_url = str(
        variant.get("external_url") or getattr(scraped_product, "url", "") or context.canonical_url
    ).strip()

    metadata = {}
    if raw_availability:
        metadata["raw_availability"] = raw_availability
    return OfferCheckResult(
        availability_status=availability,
        stock_precision=precision,
        stock_quantity=quantity,
        source_price=_decimal(price_value),
        source_currency=currency,
        canonical_url=canonical_url,
        response_metadata=metadata,
    )
