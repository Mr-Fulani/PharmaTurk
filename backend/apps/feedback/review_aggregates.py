"""Bulk aggregation helpers for product-card review summaries."""

from django.db.models import Avg, Count, Q

from .models import ProductReview


def _target_key(product_type, product_slug):
    normalized_type = str(product_type or "").strip().lower().replace("_", "-")
    normalized_slug = str(product_slug or "").strip()
    if not normalized_type or not normalized_slug:
        return None
    return normalized_type, normalized_slug


def _row_target(row):
    return _target_key(
        row.get("product_type") or row.get("_product_type"),
        row.get("favorite_parent_slug") or row.get("slug"),
    )


def attach_review_aggregates(card_rows):
    """Attach approved review count/rating to card dicts in one database query.

    Existing domain ratings (for example a book's imported rating) are retained
    when there is no approved platform review. Platform reviews take precedence
    as soon as at least one has been published.
    """
    rows = [row for row in card_rows if isinstance(row, dict)]
    targets = {
        target
        for row in rows
        if (target := _row_target(row))
    }
    if not targets:
        return card_rows

    target_filter = Q()
    for product_type, product_slug in targets:
        target_filter |= Q(product_type=product_type, product_slug=product_slug)

    summaries = (
        ProductReview.objects
        .filter(target_filter, status=ProductReview.Status.APPROVED)
        .values("product_type", "product_slug")
        .annotate(rating=Avg("rating"), reviews_count=Count("id"))
    )
    summary_by_target = {
        _target_key(summary["product_type"], summary["product_slug"]): summary
        for summary in summaries
    }
    for row in rows:
        summary = summary_by_target.get(
            _row_target(row)
        )
        if summary:
            row["rating"] = round(float(summary["rating"]), 1)
            row["reviews_count"] = summary["reviews_count"]
    return card_rows
