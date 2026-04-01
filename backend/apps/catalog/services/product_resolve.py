"""
Единая резолюция карточки товара/услуги по slug для SSR и клиентов.

Контракт ответа 200:
  - product_type: str — нормализованный тип с дефисами (как на фронте).
  - canonical_path: str — путь без префикса локали, с ведущим /product/...
  - payload: dict — тело того же detail, что и у соответствующего ViewSet.retrieve.
  - source: str — откуда взят объект (отладка): generic_product, domain_clothing, ...

Порядок поиска (зафиксирован; при смене — обновить тесты и комментарий):
  1) Product (generic каталог): активные, без теневых вариантов в external_data,
     с тем же queryset, что у ProductViewSet (включая исключение jewelry из списка
     — для retrieve get_queryset тоже исключает jewelry).
  2) Доменные ViewSet в порядке, согласованном с urls.py (один slug — один владелец
     в типичном кейсе; коллизии slug между доменами разрешаются первым совпадением).
  3) Service (uslugi).

Query-параметры пробрасываются через исходный request (в т.ч. active_variant_slug
для electronics и др., где serializer читает context из view).

Синхронизация с фронтом: BASE_PRODUCT_TYPES и TYPES_NEEDING_PATH должны совпадать
с frontend/src/lib/product.ts; build_canonical_path — с frontend/src/lib/urls.ts buildProductUrl.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404, HttpRequest
from rest_framework.request import Request as DrfRequest
from rest_framework.response import Response
from rest_framework import status


def _wsgi_request(request: HttpRequest | DrfRequest) -> HttpRequest:
    """DRF Request оборачивает HttpRequest; вложенным as_view нужен именно WSGI-запрос."""
    if isinstance(request, DrfRequest):
        return request._request
    return request

# Синхронно с frontend/src/lib/product.ts
BASE_PRODUCT_TYPES = frozenset(
    {
        "medicines",
        "supplements",
        "medical-equipment",
        "furniture",
        "tableware",
        "accessories",
        "books",
        "perfumery",
        "sports",
        "auto-parts",
        "incense",
        "bags",
        "watches",
        "cosmetics",
        "toys",
        "home-textiles",
        "stationery",
        "pet-supplies",
    }
)

TYPES_NEEDING_PATH = frozenset(
    {
        "clothing",
        "shoes",
        "electronics",
        "jewelry",
        "uslugi",
        "headwear",
        "underwear",
        "islamic-clothing",
    }
)


def deduplicate_slug(raw: str) -> str:
    """Как deduplicateSlug во frontend/src/lib/urls.ts."""
    if not raw:
        return ""
    normalized = str(raw).strip().replace("_", "-")
    parts = normalized.split("-")
    if len(parts) >= 4 and len(parts) % 2 == 0:
        half = len(parts) // 2
        first_half = "-".join(parts[:half])
        second_half = "-".join(parts[half:])
        if first_half == second_half:
            return first_half
    return normalized


def needs_type_in_path(product_type: str | None) -> bool:
    """Как needsTypeInPath() на фронте (frontend/src/lib/product.ts)."""
    normalized = (product_type or "").strip().replace("_", "-").lower()
    return bool(normalized and normalized in TYPES_NEEDING_PATH)


def build_canonical_path(product_type: str | None, slug: str | None) -> str:
    """
    Зеркало buildProductUrl (frontend/src/lib/urls.ts).
    product_type и slug — из payload/модели после нормализации.
    """
    normalized_type = (product_type or "medicines").strip().replace("_", "-").lower()
    raw_slug = (slug or "").strip()
    deduplicated = deduplicate_slug(raw_slug)
    if normalized_type == "uslugi":
        return f"/product/uslugi/{deduplicated}"
    if not needs_type_in_path(normalized_type):
        return f"/product/{deduplicated}"
    prefix = f"{normalized_type}-"
    cleaned = deduplicated
    while cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix) :]
    final_slug = cleaned or deduplicated
    return f"/product/{normalized_type}/{final_slug}"


def _normalize_pt(value: Any) -> str:
    if value is None:
        return "medicines"
    s = str(value).strip().replace("_", "-").lower()
    return s or "medicines"


def _dispatch_retrieve(viewset_class: type, request: HttpRequest | DrfRequest, slug: str) -> dict | None:
    """
    Вызывает тот же retrieve, что и роутер DRF, возвращает data или None при 404.
    """
    handler = viewset_class.as_view({"get": "retrieve"})
    wsgi = _wsgi_request(request)
    try:
        drf_response = handler(wsgi, slug=slug)
    except Http404:
        return None
    if drf_response.status_code != status.HTTP_200_OK:
        return None
    if not hasattr(drf_response, "data"):
        return None
    data = drf_response.data
    if not isinstance(data, dict):
        return None
    return data


def _domain_viewsets_order():
    """Ленивый импорт, чтобы избежать циклов при загрузке views."""
    from apps.catalog import views as v

    return [
        (v.ClothingProductViewSet, "domain_clothing"),
        (v.ShoeProductViewSet, "domain_shoes"),
        (v.ElectronicsProductViewSet, "domain_electronics"),
        (v.JewelryProductViewSet, "domain_jewelry"),
        (v.FurnitureProductViewSet, "domain_furniture"),
        (v.BookProductViewSet, "domain_books"),
        (v.PerfumeryProductViewSet, "domain_perfumery"),
        (v.MedicineProductViewSet, "domain_medicines"),
        (v.SupplementProductViewSet, "domain_supplements"),
        (v.MedicalEquipmentProductViewSet, "domain_medical_equipment"),
        (v.TablewareProductViewSet, "domain_tableware"),
        (v.AccessoryProductViewSet, "domain_accessories"),
        (v.IncenseProductViewSet, "domain_incense"),
        (v.SportsProductViewSet, "domain_sports"),
        (v.AutoPartProductViewSet, "domain_auto_parts"),
        (v.HeadwearProductViewSet, "domain_headwear"),
        (v.UnderwearProductViewSet, "domain_underwear"),
        (v.IslamicClothingProductViewSet, "domain_islamic_clothing"),
    ]


def resolve_product_payload(request: HttpRequest | DrfRequest, slug: str) -> tuple[dict, str, str] | None:
    """
    Возвращает (payload, source, product_type_normalized) или None.

    product_type_normalized — дефисы, для canonical_path и фронта.
    """
    if not slug or not str(slug).strip():
        return None

    slug = str(slug).strip()

    # 1) Generic Product
    from apps.catalog.views import ProductViewSet, ServiceViewSet

    data = _dispatch_retrieve(ProductViewSet, request, slug)
    if data is not None:
        pt = _normalize_pt(data.get("product_type"))
        return data, "generic_product", pt

    # 2) Домены
    for view_cls, source_key in _domain_viewsets_order():
        data = _dispatch_retrieve(view_cls, request, slug)
        if data is not None:
            pt = _normalize_pt(data.get("product_type"))
            return data, source_key, pt

    # 3) Услуги (URL в каталоге: /services/{slug}/)
    data = _dispatch_retrieve(ServiceViewSet, request, slug)
    if data is not None:
        return data, "domain_service", "uslugi"

    return None


def build_resolve_response(request: HttpRequest | DrfRequest, slug: str) -> Response:
    resolved = resolve_product_payload(request, slug)
    if resolved is None:
        return Response({"detail": "Товар не найден."}, status=status.HTTP_404_NOT_FOUND)

    payload, source, product_type = resolved
    slug_for_url = payload.get("slug") or slug
    canonical = build_canonical_path(product_type, str(slug_for_url))

    body = {
        "product_type": product_type,
        "canonical_path": canonical,
        "payload": payload,
        "source": source,
    }
    return Response(body, status=status.HTTP_200_OK)
