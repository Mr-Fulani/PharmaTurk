"""Read-only Akakce market availability adapter for dietary supplements.

Akakce is a price-comparison page, not a warehouse.  The adapter therefore
reports boolean availability only when the saved product page publishes at
least one current, priced, in-stock seller offer in JSON-LD.  It never invents
stock quantities and never follows seller URLs.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Iterator, List, Optional
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from apps.http_errors import ExternalAccessBlockedError

from ..base.offers import (
    MalformedOfferResponse,
    OfferAvailability,
    OfferCheckContext,
    OfferCheckResult,
    OfferNotFound,
    OfferStockPrecision,
    translate_offer_check_errors,
)
from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text


_TURKISH_ASCII = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
)
_IDENTITY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_GENERIC_TOKENS = frozenset(
    {
        "takviye",
        "edici",
        "gida",
        "urun",
        "yeni",
        "icin",
    }
)


def normalize_akakce_identity(value: Any) -> str:
    """Return a stable Turkish/ASCII identity string for conservative matching."""

    translated = str(value or "").translate(_TURKISH_ASCII).casefold()
    decomposed = unicodedata.normalize("NFKD", translated)
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_IDENTITY_TOKEN_RE.findall(ascii_value))


def akakce_product_match_score(expected: Any, observed: Any) -> Decimal | None:
    """Score only strong product-title matches, preserving dosage/count identity.

    Numeric signatures must be identical.  This intentionally rejects tempting
    but unsafe substitutions such as 30 vs 60 tablets or 20 vs 50 ml.
    """

    expected_normalized = normalize_akakce_identity(expected)
    observed_normalized = normalize_akakce_identity(observed)
    if not expected_normalized or not observed_normalized:
        return None

    expected_numbers = tuple(_NUMBER_RE.findall(expected_normalized))
    observed_numbers = tuple(_NUMBER_RE.findall(observed_normalized))
    if expected_numbers != observed_numbers:
        return None

    expected_tokens = {
        token
        for token in expected_normalized.split()
        if token not in _GENERIC_TOKENS and (len(token) >= 2 or token.isdigit())
    }
    observed_tokens = {
        token
        for token in observed_normalized.split()
        if token not in _GENERIC_TOKENS and (len(token) >= 2 or token.isdigit())
    }
    distinctive = {token for token in expected_tokens if len(token) >= 4 and not token.isdigit()}
    if not expected_tokens or not distinctive:
        return None

    coverage = Decimal(len(expected_tokens & observed_tokens)) / Decimal(len(expected_tokens))
    sequence = Decimal(
        str(SequenceMatcher(None, expected_normalized, observed_normalized).ratio())
    )
    if not expected_numbers:
        observed_distinctive = {
            token for token in observed_tokens if len(token) >= 4 and not token.isdigit()
        }
        if observed_distinctive - distinctive:
            return None
    # Akakce sometimes repeats the brand ("IMUPLUS Imuplus ...").  Full token
    # coverage is therefore stronger evidence than raw sequence similarity.
    if coverage < Decimal("0.85"):
        return None
    if sequence < Decimal("0.60") and expected_normalized not in observed_normalized:
        return None
    return (coverage * Decimal("0.75") + sequence * Decimal("0.25")).quantize(
        Decimal("0.0001")
    )


@dataclass(frozen=True)
class AkakceSearchCandidate:
    name: str
    url: str
    external_id: str


@dataclass(frozen=True)
class AkakceSellerOffer:
    seller_name: str
    seller_url: str
    price: Decimal
    currency: str


@dataclass(frozen=True)
class AkakceProductSnapshot:
    name: str
    canonical_url: str
    external_id: str
    offers: tuple[AkakceSellerOffer, ...]

    @property
    def selected_offer(self) -> AkakceSellerOffer | None:
        return min(self.offers, key=lambda row: (row.price, row.seller_name)) if self.offers else None


class AkakceParser(BaseScraper):
    """Strict parser for saved Akakce ``/vitamin-mineral/`` product pages."""

    PRODUCT_PATH_RE = re.compile(
        r"^/vitamin-mineral/en-ucuz-[^/?#]+-fiyati,(\d+)\.html$",
        re.IGNORECASE,
    )
    CHALLENGE_MARKERS = (
        "cf-chl-",
        "captcha",
        "access denied",
        "erişim engellendi",
    )
    FIXED_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )

    def __init__(self, base_url: str = "https://www.akakce.com", **kwargs):
        kwargs.setdefault("delay_range", (1, 2))
        super().__init__(base_url=base_url, **kwargs)
        self.configure_request_identity(
            user_agent=self.FIXED_USER_AGENT,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://www.google.com/",
            },
        )

    def get_name(self) -> str:
        return "akakce"

    def get_supported_domains(self) -> List[str]:
        return ["akakce.com", "www.akakce.com"]

    @classmethod
    def _external_id(cls, url: str) -> str:
        match = cls.PRODUCT_PATH_RE.match(urlparse(str(url or "")).path)
        return match.group(1) if match else ""

    @classmethod
    def canonical_product_url(cls, url: str) -> str | None:
        try:
            parsed = urlparse(str(url or "").strip())
            port = parsed.port
        except ValueError:
            return None
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username
            or parsed.password
            or port not in {None, 443}
            or hostname not in {"akakce.com", "www.akakce.com"}
            or not cls.PRODUCT_PATH_RE.match(parsed.path)
        ):
            return None
        return urlunparse(("https", "www.akakce.com", parsed.path, "", "", ""))

    @staticmethod
    def _looks_like_challenge(html: str) -> bool:
        lowered = str(html or "").casefold()
        return any(marker in lowered for marker in AkakceParser.CHALLENGE_MARKERS)

    @staticmethod
    def _json_ld_nodes(value: Any) -> Iterator[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            graph = value.get("@graph")
            if isinstance(graph, list):
                for row in graph:
                    yield from AkakceParser._json_ld_nodes(row)
        elif isinstance(value, list):
            for row in value:
                yield from AkakceParser._json_ld_nodes(row)

    @classmethod
    def _product_payload(cls, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html or "", "html.parser")
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            for node in cls._json_ld_nodes(payload):
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if "Product" in types and clean_text(str(node.get("name") or "")):
                    return node
        raise MalformedOfferResponse("Akakce response does not contain Product JSON-LD")

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not amount.is_finite() or amount <= 0:
            return None
        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def _trusted_seller_url(value: Any) -> str:
        try:
            parsed = urlparse(str(value or "").strip())
            port = parsed.port
        except ValueError:
            return ""
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or port not in {None, 443}
        ):
            return ""
        return urlunparse(parsed._replace(fragment=""))[:2000]

    @classmethod
    def _seller_offers(cls, product: dict[str, Any]) -> tuple[AkakceSellerOffer, ...]:
        aggregate = product.get("offers")
        if not isinstance(aggregate, dict) or aggregate.get("@type") != "AggregateOffer":
            return ()
        rows = aggregate.get("offers")
        if not isinstance(rows, list):
            return ()

        offers: list[AkakceSellerOffer] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("@type") != "Offer":
                continue
            availability = str(row.get("availability") or "").rstrip("/").casefold()
            currency = str(row.get("priceCurrency") or "").strip().upper()
            price = cls._money(row.get("price"))
            seller_url = cls._trusted_seller_url(row.get("url"))
            seller = row.get("seller") if isinstance(row.get("seller"), dict) else {}
            seller_name = clean_text(str(seller.get("name") or ""))[:200]
            if (
                not availability.endswith("/instock")
                or currency != "TRY"
                or price is None
                or not seller_url
                or not seller_name
            ):
                continue
            offers.append(
                AkakceSellerOffer(
                    seller_name=seller_name,
                    seller_url=seller_url,
                    price=price,
                    currency=currency,
                )
            )
        return tuple(offers)

    @translate_offer_check_errors
    def search_products(self, query: str, *, max_results: int = 5) -> list[AkakceSearchCandidate]:
        normalized_query = clean_text(str(query or ""))[:250]
        if len(normalized_query) < 3:
            return []
        search_url = f"{self.base_url}/arama/?{urlencode({'q': normalized_query})}"
        html = self._make_offer_request(search_url)
        if self._looks_like_challenge(html):
            raise ExternalAccessBlockedError(source="Akakce", status_code=403, url=search_url)

        soup = BeautifulSoup(html, "html.parser")
        candidates: list[AkakceSearchCandidate] = []
        seen: set[str] = set()
        # ``a.iC`` is the actual matching result.  Other product anchors on the
        # page are recommendations/popular products and must not be candidates.
        for anchor in soup.select("a.iC[href]"):
            canonical = self.canonical_product_url(urljoin(self.base_url, anchor.get("href", "")))
            name = clean_text(str(anchor.get("title") or anchor.get_text(" ", strip=True) or ""))
            if not canonical or not name or canonical in seen:
                continue
            seen.add(canonical)
            candidates.append(
                AkakceSearchCandidate(
                    name=name,
                    url=canonical,
                    external_id=self._external_id(canonical),
                )
            )
            if len(candidates) >= max(1, min(int(max_results), 10)):
                break
        return candidates

    def _load_snapshot(self, context: OfferCheckContext) -> AkakceProductSnapshot:
        requested_url = self.canonical_product_url(context.canonical_url)
        if not requested_url:
            raise OfferNotFound(context.canonical_url)
        html, final_url = self._make_offer_request(requested_url, include_final_url=True)
        if self._looks_like_challenge(html):
            raise ExternalAccessBlockedError(
                source="Akakce",
                status_code=403,
                url=requested_url,
            )
        canonical_final = self.canonical_product_url(final_url)
        requested_id = self._external_id(requested_url)
        final_id = self._external_id(canonical_final or "")
        if not canonical_final or not requested_id or requested_id != final_id:
            raise OfferNotFound(requested_url)
        if context.external_product_id and str(context.external_product_id) != final_id:
            raise OfferNotFound(requested_url)

        product = self._product_payload(html)
        name = clean_text(str(product.get("name") or ""))
        expected_name = str(context.parser_config.get("expected_name") or "").strip()
        if not expected_name:
            raise MalformedOfferResponse("Saved Akakce offer has no expected product identity")
        if akakce_product_match_score(expected_name, name) is None:
            raise MalformedOfferResponse("Akakce product identity does not match saved product")

        return AkakceProductSnapshot(
            name=name,
            canonical_url=canonical_final,
            external_id=final_id,
            offers=self._seller_offers(product),
        )

    @translate_offer_check_errors
    def inspect_offer(self, context: OfferCheckContext) -> AkakceProductSnapshot:
        """Load and validate a product page even when it currently has no sellers."""

        return self._load_snapshot(context)

    @translate_offer_check_errors
    def check_offer(self, offer: OfferCheckContext) -> OfferCheckResult:
        snapshot = self._load_snapshot(offer)
        selected = snapshot.selected_offer
        if selected is None:
            # The product identity exists, but no priced seller is currently
            # available.  A typed terminal absence blocks cart/checkout.
            raise OfferNotFound(snapshot.canonical_url)
        return OfferCheckResult(
            availability_status=OfferAvailability.IN_STOCK,
            stock_precision=OfferStockPrecision.BOOLEAN,
            canonical_url=snapshot.canonical_url,
            source_price=selected.price,
            source_currency=selected.currency,
            stock_quantity=None,
            response_metadata={
                "marketplace": "akakce",
                "market_product_name": snapshot.name,
                "market_product_id": snapshot.external_id,
                "seller_name": selected.seller_name,
                "seller_url": selected.seller_url,
                "in_stock_seller_count": len(snapshot.offers),
                "availability_evidence": "json_ld_offer_in_stock",
            },
        )

    def parse_product_list(self, category_url: str, max_pages: int = 10) -> List[ScrapedProduct]:
        # This adapter is intentionally demand-driven; it is not a catalogue crawler.
        return []

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        canonical = self.canonical_product_url(product_url)
        if not canonical:
            return None
        # Full-import callers do not own a trusted catalogue identity, therefore
        # product detail import remains unsupported.  Live checks use inspect/check.
        return None
