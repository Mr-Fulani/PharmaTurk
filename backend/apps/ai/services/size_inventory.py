"""Safe extraction and application of apparel size inventory.

Sizes are not ordinary descriptive attributes in the catalog: supported
apparel domains store them in related ``*ProductSize`` rows, while products
with variants store them per variant.  This module keeps that distinction in
one place so AI processing cannot accidentally write apparel sizes into an
unrelated category or guess a variant association.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from apps.catalog.attribute_specs import normalize_product_type


SIZE_INVENTORY_PRODUCT_TYPES = frozenset(
    {"clothing", "shoes", "headwear", "underwear", "islamic_clothing"}
)

_SIZE_CONTEXT_RE = re.compile(
    r"\b(?:размер(?:ы|а|ов|ах|е)?|sizes?|beden(?:ler|leri)?)\b",
    re.IGNORECASE,
)
_NEGATIVE_SIZE_RE = re.compile(
    r"(?:нет\s+в\s+наличии|закончились|отсутствуют|out\s+of\s+stock|unavailable|t[uü]kendi)",
    re.IGNORECASE,
)
_EXPLICIT_AVAILABLE_RE = re.compile(
    r"(?:в\s+наличии|остал(?:ся|ись|ось)|доступн|available|in\s+stock|mevcut|stokta)",
    re.IGNORECASE,
)
_PRICE_BOUNDARY_RE = re.compile(
    r"(?:стоимост|цен[аы]|price|fiyat|₽|\$|€|₺|\b(?:rub|try|tl|usd|eur|kzt)\b)",
    re.IGNORECASE,
)
_SIZE_TOKEN_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9])(?:"
    r"one[\s-]?size|tek[\s-]?beden|standard|"
    r"[2-9]xl|x{1,4}[sml]|[sml]|"
    r"\d{2,3}[a-h]|"
    r"\d{1,3}(?:[.,]\d)?(?:\s*[-–—/]\s*\d{1,3}(?:[.,]\d)?)?"
    r")(?![A-Za-zА-Яа-яЁё0-9])",
    re.IGNORECASE,
)
_STOCK_URGENCY_RE = re.compile(
    r"(?:"
    r"\b(?:поспешите|успейте)\b|"
    r"\bhurry(?:\s+up)?\b|"
    r"\bwhile\s+(?:stocks?|supplies)\s+last\b|"
    r"\bостал(?:ся|ись|ось)\b[^.!?]*\b\d+\b[^.!?]*"
    r"\b(?:комплект\w*|штук\w*|товар\w*)\b|"
    r"\bonly\s+\d+\b[^.!?]*\b(?:sets?|items?|pieces?)\b[^.!?]*\bleft\b|"
    r"\b(?:последн\w*)\s+(?:комплект\w*|штук\w*|товар\w*)\b|"
    r"\b(?:last)\s+(?:sets?|items?|pieces?)\b"
    r")",
    re.IGNORECASE,
)


def supports_size_inventory(product_type: str | None) -> bool:
    return normalize_product_type(product_type) in SIZE_INVENTORY_PRODUCT_TYPES


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().casefold() not in {
            "",
            "0",
            "false",
            "no",
            "нет",
            "hayır",
        }
    return bool(value)


def size_identity(value: Any) -> str:
    """Return a comparison key; ``XXL`` and ``2XL`` are the same size."""
    normalized = str(value or "").strip().upper().replace(" ", "")
    normalized = normalized.replace("–", "-").replace("—", "-")
    if normalized in {"ONESIZE", "ONE-SIZE", "STANDARD", "TEKBEDEN", "TEK-BEDEN"}:
        return "ONE_SIZE"
    numeric_xl = re.fullmatch(r"([2-9])XL", normalized)
    if numeric_xl:
        return "X" * int(numeric_xl.group(1)) + "L"
    return normalized.replace(",", ".")


def normalize_size_value(value: Any, product_type: str | None = None) -> str:
    raw = str(value or "").strip().upper()
    raw = re.sub(r"\s+", "", raw).replace("–", "-").replace("—", "-")
    if raw in {"ONESIZE", "ONE-SIZE", "STANDARD", "TEKBEDEN", "TEK-BEDEN"}:
        return "ONE SIZE"
    if re.fullmatch(r"(?:[2-9]XL|X{1,4}[SML]|[SML])", raw):
        return raw
    if re.fullmatch(r"\d{2,3}[A-H]", raw):
        number = int(raw[:-1])
        if 50 <= number <= 130:
            return raw
        return ""

    numeric_parts = re.split(r"[-/]", raw.replace(",", "."))
    if not numeric_parts or not all(re.fullmatch(r"\d{1,3}(?:\.\d)?", part) for part in numeric_parts):
        return ""
    values = [float(part) for part in numeric_parts]
    normalized_type = normalize_product_type(product_type)
    if normalized_type == "shoes":
        lower, upper = 15, 55
    elif normalized_type == "headwear":
        lower, upper = 35, 80
    else:
        lower, upper = 20, 200
    if not all(lower <= value <= upper for value in values):
        return ""
    return raw.replace(".", ",") if "." in raw else raw


def _source_texts(input_data: dict[str, Any]) -> Iterable[str]:
    for key in ("name", "description", "raw_description"):
        value = input_data.get(key)
        if value:
            yield str(value)
    for key in ("attributes", "source_attributes"):
        value = input_data.get(key)
        if value:
            yield json.dumps(value, ensure_ascii=False)


def _context_segments(text: str) -> Iterable[tuple[str, bool]]:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+|#+", str(text or "")):
        if not sentence or not _SIZE_CONTEXT_RE.search(sentence):
            continue
        if _NEGATIVE_SIZE_RE.search(sentence):
            # Negative inventory claims must not make rows unavailable: that
            # decision is too destructive without a dedicated stock feed.
            continue
        explicit_available = bool(_EXPLICIT_AVAILABLE_RE.search(sentence))
        for context in _SIZE_CONTEXT_RE.finditer(sentence):
            after = sentence[context.end() : context.end() + 140]
            price_boundary = _PRICE_BOUNDARY_RE.search(after)
            if price_boundary:
                after = after[: price_boundary.start()]
            yield after, explicit_available

            # Turkish sources commonly put ``beden`` after the values:
            # ``M, XL beden``. Restrict this fallback to the short prefix.
            before = sentence[max(0, context.start() - 80) : context.start()]
            price_boundary = _PRICE_BOUNDARY_RE.search(before)
            if price_boundary:
                before = before[price_boundary.end() :]
            yield before, explicit_available


def extract_sizes_from_input(
    input_data: dict[str, Any] | None,
    product_type: str | None = None,
) -> list[dict[str, Any]]:
    data = input_data if isinstance(input_data, dict) else {}
    normalized_type = normalize_product_type(product_type or data.get("product_type"))
    if normalized_type not in SIZE_INVENTORY_PRODUCT_TYPES:
        return []

    result: list[dict[str, Any]] = []
    identities: set[str] = set()
    for text in _source_texts(data):
        for segment, explicit_available in _context_segments(text):
            for match in _SIZE_TOKEN_RE.finditer(segment):
                display = normalize_size_value(match.group(0), normalized_type)
                identity = size_identity(display)
                if not display or identity in identities:
                    continue
                identities.add(identity)
                result.append(
                    {
                        "size": display,
                        "is_available": True,
                        "availability_explicit": explicit_available,
                        "stock_quantity": None,
                        "source": "source_text",
                        "confidence": 1.0,
                    }
                )
    return result


def normalize_size_rows(
    raw_rows: Any,
    product_type: str | None,
) -> list[dict[str, Any]]:
    if not supports_size_inventory(product_type):
        return []
    if isinstance(raw_rows, (str, int, float)):
        raw_rows = [raw_rows]
    if not isinstance(raw_rows, list):
        return []

    result: list[dict[str, Any]] = []
    identities: set[str] = set()
    for raw in raw_rows:
        row = raw if isinstance(raw, dict) else {"size": raw}
        display = normalize_size_value(row.get("size") or row.get("value"), product_type)
        identity = size_identity(display)
        if not display or identity in identities:
            continue
        identities.add(identity)
        source = str(row.get("source") or "ai").strip().lower()
        try:
            confidence = float(row.get("confidence", 1.0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        result.append(
            {
                "size": display,
                "is_available": _as_bool(row.get("is_available"), default=True),
                "availability_explicit": _as_bool(row.get("availability_explicit")),
                "stock_quantity": None,
                "source": source,
                "confidence": confidence,
            }
        )
    return result


def merge_confirmed_sizes(
    attributes: dict[str, Any] | None,
    input_data: dict[str, Any] | None,
    product_type: str | None,
    *,
    allow_moderator_override: bool = False,
) -> dict[str, Any]:
    """Merge deterministic source extraction with confirmed AI/moderator rows.

    AI-proposed sizes that are absent from the source are dropped. A separate
    moderator override is honored only when the trusted review/apply path opts
    into it explicitly.
    """
    attrs = dict(attributes or {})
    if not supports_size_inventory(product_type):
        attrs.pop("sizes", None)
        attrs.pop("moderator_sizes", None)
        return attrs

    if allow_moderator_override and "moderator_sizes" in attrs:
        attrs["sizes"] = normalize_size_rows(attrs.get("moderator_sizes"), product_type)
        return attrs
    # This key is never accepted from an LLM response. It is created only by
    # the trusted moderation form and enabled explicitly at review/apply time.
    attrs.pop("moderator_sizes", None)

    source_rows = extract_sizes_from_input(input_data, product_type)
    source_identities = {size_identity(row["size"]) for row in source_rows}
    proposed_rows = normalize_size_rows(attrs.get("sizes"), product_type)
    merged = list(source_rows)
    seen = set(source_identities)
    for row in proposed_rows:
        identity = size_identity(row["size"])
        if identity not in source_identities:
            continue
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(row)
    attrs["sizes"] = merged
    return attrs


def parse_moderator_size_list(value: Any, product_type: str | None) -> list[dict[str, Any]]:
    tokens = re.split(r"[,;\n]+", str(value or ""))
    rows = [
        {
            "size": token.strip(),
            "is_available": True,
            "availability_explicit": True,
            "source": "moderator",
            "confidence": 1.0,
        }
        for token in tokens
        if token.strip()
    ]
    return normalize_size_rows(rows, product_type)


def target_has_variants(target: Any) -> bool:
    manager = getattr(target, "variants", None)
    if manager is None:
        return False
    try:
        return manager.exists()
    except Exception:
        return False


def size_inventory_block_reason(
    target: Any,
    product_type: str | None,
    rows: Any,
) -> str:
    normalized = normalize_size_rows(rows, product_type)
    if not normalized:
        return ""
    if not supports_size_inventory(product_type) or not hasattr(target, "sizes"):
        return "unsupported_sizes"
    if target_has_variants(target):
        return "ambiguous_variant_sizes"
    return ""


def current_product_sizes(target: Any) -> list[str]:
    manager = getattr(target, "sizes", None)
    if manager is None:
        return []
    try:
        return [
            str(value).strip()
            for value in manager.order_by("sort_order", "id").values_list("size", flat=True)
            if str(value or "").strip()
        ]
    except Exception:
        return []


def apply_size_inventory(
    target: Any,
    rows: Any,
    product_type: str | None,
) -> bool:
    normalized_rows = normalize_size_rows(rows, product_type)
    if not normalized_rows or size_inventory_block_reason(target, product_type, normalized_rows):
        return False

    # Serialize AI applications for the same domain product. The schema has no
    # uniqueness constraint on legacy size tables, so this lock also keeps
    # repeated/concurrent applications idempotent within this workflow.
    target.__class__.objects.select_for_update().get(pk=target.pk)
    existing_rows = list(target.sizes.all())
    existing_by_identity: dict[str, Any] = {}
    max_order = 0
    for existing in existing_rows:
        identity = size_identity(existing.size)
        if identity and identity not in existing_by_identity:
            existing_by_identity[identity] = existing
        max_order = max(max_order, int(existing.sort_order or 0))

    updated = False
    for offset, row in enumerate(normalized_rows, start=1):
        identity = size_identity(row["size"])
        existing = existing_by_identity.get(identity)
        if existing is None:
            existing = target.sizes.create(
                size=row["size"],
                is_available=bool(row.get("is_available", True)),
                stock_quantity=None,
                sort_order=max_order + offset,
            )
            existing_by_identity[identity] = existing
            updated = True
            continue
        if row.get("availability_explicit") and existing.is_available != row["is_available"]:
            existing.is_available = row["is_available"]
            existing.save(update_fields=["is_available", "updated_at"])
            updated = True
        # Existing stock_quantity, spelling and sort order are deliberately
        # preserved. Unmentioned size rows are never deleted.
    return updated


def strip_size_inventory_sentences(text: Any) -> str:
    """Remove apparel size/stock urgency while preserving stable product copy."""
    source = str(text or "").strip()
    if not source:
        return ""
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
        candidate = sentence.strip()
        if not candidate:
            continue
        has_context = bool(_SIZE_CONTEXT_RE.search(candidate))
        has_size_token = any(
            normalize_size_value(match.group(0), "clothing")
            for match in _SIZE_TOKEN_RE.finditer(candidate)
        )
        inventory_wording = bool(
            re.search(
                r"(?:в\s+наличии|остал(?:ся|ись|ось)|доступн|available|in\s+stock|размер|sizes?|beden)",
                candidate,
                re.IGNORECASE,
            )
        )
        if has_context and (has_size_token or inventory_wording):
            continue
        if _STOCK_URGENCY_RE.search(candidate):
            continue
        kept.append(candidate)
    return re.sub(r"\s{2,}", " ", " ".join(kept)).strip()
