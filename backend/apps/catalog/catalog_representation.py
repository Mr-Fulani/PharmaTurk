"""Shared representation contract for public catalog serializers."""

from __future__ import annotations

from .seo_defaults import resolve_book_seo_value
from .services.source_offer_catalog_projection import (
    apply_source_offer_catalog_projection,
)


def _request_lang(request) -> str:
    return getattr(request, "LANGUAGE_CODE", "ru") if request else "ru"


class LocalizedSeoMethodsMixin:
    """Apply common SEO, pricing and source-availability representation rules."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not getattr(self, "_normalizes_public_prices", False):
            # Keep the established serializers module as the compatibility seam
            # for tests and callers that patch the legacy pricing adapter.
            from .serializers import _apply_product_markup_to_payload

            data = _apply_product_markup_to_payload(data, instance)

        # This projection is DB-only and detail-only. List serializers therefore
        # acquire neither an N+1 query nor supplier HTTP requests.
        return apply_source_offer_catalog_projection(data, instance, self.context)

    def _resolve_localized_seo(self, obj, field_name: str):
        request = self.context.get("request")
        return resolve_book_seo_value(
            obj,
            field_name,
            lang=_request_lang(request),
        )

    def get_meta_title(self, obj):
        return self._resolve_localized_seo(obj, "meta_title")

    def get_meta_description(self, obj):
        return self._resolve_localized_seo(obj, "meta_description")

    def get_meta_keywords(self, obj):
        return self._resolve_localized_seo(obj, "meta_keywords")

    def get_og_title(self, obj):
        return self._resolve_localized_seo(obj, "og_title")

    def get_og_description(self, obj):
        return self._resolve_localized_seo(obj, "og_description")

    def get_og_image_url(self, obj):
        return self._resolve_localized_seo(obj, "og_image_url")
