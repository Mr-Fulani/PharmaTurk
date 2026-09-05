"""Read-only public projection for medicine analog references."""

import logging

from django.db import models
from django.db.models import Q

from .models import MedicineProduct
from .serializers import MedicineProductImageSerializer


logger = logging.getLogger(__name__)


def build_medicine_reference_payload(product, request, limit):
    """Build the existing public analog/reference response for a medicine."""
    preferred_currency = (
        request.headers.get("X-Currency")
        or request.query_params.get("currency")
        or "TRY"
    ).upper()

    active_ingredient = (product.active_ingredient or "").strip()
    atc_code = (product.atc_code or "").strip()
    sgk_equivalent_code = (product.sgk_equivalent_code or "").strip()

    query = Q()
    has_filters = False
    if active_ingredient:
        query |= Q(active_ingredient__iexact=active_ingredient)
        has_filters = True
    if atc_code:
        query |= Q(atc_code__iexact=atc_code)
        has_filters = True
    if sgk_equivalent_code:
        query |= Q(sgk_equivalent_code__iexact=sgk_equivalent_code)
        has_filters = True

    explicit_refs = list(product.analogs.all())
    for reference in explicit_refs:
        reference_query = Q()
        if reference.analog_product_id:
            reference_query |= Q(pk=reference.analog_product_id)
        if reference.barcode:
            reference_query |= Q(barcode=reference.barcode)
        if reference.external_id:
            reference_query |= Q(external_id=reference.external_id)
        if reference.sgk_equivalent_code:
            reference_query |= Q(
                sgk_equivalent_code=reference.sgk_equivalent_code
            )
        if reference.name:
            reference_query |= Q(name__iexact=reference.name)
        if reference_query.children:
            query |= reference_query
            has_filters = True

    if not has_filters:
        return {
            "count": 0,
            "active_ingredient": None,
            "atc_code": None,
            "results": [],
        }

    analogs = (
        MedicineProduct.objects.filter(query, is_active=True)
        .exclude(
            models.Q(external_data__has_key="is_stub")
            & models.Q(external_data__is_stub=True)
        )
        .exclude(pk=product.pk)
        .select_related("brand", "category")
        .prefetch_related("gallery_images")
        .order_by("-is_available", "price")[:limit]
    )

    try:
        from .utils.currency_converter import currency_converter
    except Exception:
        currency_converter = None

    def convert(price, from_currency, priced_product):
        if price is None:
            return None
        if currency_converter is None:
            from .utils.product_markup import apply_product_markup

            return float(apply_product_markup(price, priced_product))
        try:
            _original, _converted, price_with_margin = (
                currency_converter.convert_price(
                    price,
                    from_currency or "TRY",
                    preferred_currency,
                    apply_margin=True,
                )
            )
            from .utils.product_markup import apply_product_markup

            return float(apply_product_markup(price_with_margin, priced_product))
        except Exception:
            logger.exception(
                "Failed to calculate public analog price for product_id=%s",
                getattr(priced_product, "pk", None),
            )
            try:
                from .utils.product_markup import apply_product_markup

                return float(apply_product_markup(price, priced_product))
            except Exception:
                return float(price)

    current_price = convert(
        product.price,
        product.currency or "TRY",
        product,
    )
    results = []
    matched_reference_ids = set()

    def reference_for(analog):
        for reference in explicit_refs:
            if reference.analog_product_id == analog.pk:
                return reference
            if (
                reference.barcode
                and analog.barcode
                and reference.barcode == analog.barcode
            ):
                return reference
            if (
                reference.external_id
                and analog.external_id
                and reference.external_id == analog.external_id
            ):
                return reference
            if reference.name and reference.name.casefold() == (
                analog.name or ""
            ).casefold():
                return reference
        return None

    for analog in analogs:
        source_reference = reference_for(analog)
        if source_reference:
            matched_reference_ids.add(source_reference.pk)

        main_image = analog.main_image or ""
        if not main_image:
            first_gallery = analog.gallery_images.first()
            if first_gallery:
                main_image = first_gallery.image_url or ""
        if main_image and request and not main_image.startswith("http"):
            main_image = request.build_absolute_uri(main_image)

        analog_price = convert(
            analog.price,
            analog.currency or "TRY",
            analog,
        )
        analog_old_price = convert(
            analog.old_price,
            analog.currency or "TRY",
            analog,
        )
        saving_percent = None
        saving_amount = None
        if current_price and analog_price and analog_price < current_price:
            saving_amount = round(current_price - analog_price, 2)
            saving_percent = round(saving_amount / current_price * 100)

        results.append(
            {
                "id": analog.pk,
                "slug": analog.slug,
                "name": analog.name,
                "brand": analog.brand.name if analog.brand else None,
                "price": round(analog_price, 2) if analog_price else None,
                "old_price": (
                    round(analog_old_price, 2) if analog_old_price else None
                ),
                "original_price": (
                    float(analog.price) if analog.price else None
                ),
                "original_currency": analog.currency or "TRY",
                "display_currency": preferred_currency,
                "is_available": analog.is_available,
                "main_image_url": main_image or None,
                "images": MedicineProductImageSerializer(
                    analog.gallery_images.all(),
                    many=True,
                    context={"request": request},
                ).data,
                "dosage_form": analog.dosage_form or None,
                "active_ingredient": analog.active_ingredient or None,
                "saving_percent": saving_percent,
                "saving_amount": saving_amount,
                "is_catalog_product": True,
                "reference_id": (
                    source_reference.pk if source_reference else None
                ),
                "source_reference_price": (
                    float(source_reference.reference_price)
                    if source_reference
                    and source_reference.reference_price is not None
                    else None
                ),
                "source_reference_currency": (
                    source_reference.reference_currency or None
                    if source_reference
                    else None
                ),
                "source_last_observed_at": (
                    source_reference.last_observed_at
                    if source_reference
                    else None
                ),
            }
        )

    unresolved_refs = sorted(
        (
            reference
            for reference in explicit_refs
            if reference.analog_product_id is None
            and reference.pk not in matched_reference_ids
        ),
        key=lambda reference: (
            reference.last_observed_at is None,
            -(
                reference.last_observed_at.timestamp()
                if reference.last_observed_at
                else 0
            ),
            reference.name.casefold(),
        ),
    )
    for reference in unresolved_refs:
        if len(results) >= limit:
            break
        results.append(
            {
                "id": None,
                "reference_id": reference.pk,
                "slug": None,
                "name": reference.name,
                "brand": None,
                "price": None,
                "old_price": None,
                "original_price": (
                    float(reference.reference_price)
                    if reference.reference_price is not None
                    else None
                ),
                "original_currency": reference.reference_currency or "TRY",
                "display_currency": reference.reference_currency or "TRY",
                "is_available": None,
                "main_image_url": None,
                "images": [],
                "dosage_form": None,
                "active_ingredient": active_ingredient or None,
                "saving_percent": None,
                "saving_amount": None,
                "is_catalog_product": False,
                "source_reference_price": (
                    float(reference.reference_price)
                    if reference.reference_price is not None
                    else None
                ),
                "source_reference_currency": (
                    reference.reference_currency or None
                ),
                "source_last_observed_at": reference.last_observed_at,
            }
        )

    return {
        "count": len(results),
        "active_ingredient": active_ingredient or None,
        "atc_code": atc_code or None,
        "sgk_equivalent_code": sgk_equivalent_code or None,
        "display_currency": preferred_currency,
        "results": results,
    }
