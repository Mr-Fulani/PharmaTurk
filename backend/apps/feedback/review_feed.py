from collections import defaultdict

from django.db.models import (
    Case,
    CharField,
    DateTimeField,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from .models import ProductReview, ProductReviewMedia, Testimonial, TestimonialMedia
from .serializers import ProductReviewSerializer, ReviewFeedItemSerializer, TestimonialSerializer


PLATFORM_SOURCE = "testimonial"
PRODUCT_SOURCE = "product_review"
PLATFORM_REVIEW_TYPE = "platform"
PRODUCT_REVIEW_TYPE = "product"
SERVICE_REVIEW_TYPE = "service"


def build_review_feed_rows(*, placement: str, username: str = ""):
    """Return a database-ordered union of visible review identities."""

    testimonials = Testimonial.objects.filter(is_active=True).order_by()
    product_reviews = ProductReview.objects.filter(status=ProductReview.Status.APPROVED).order_by()

    if placement == "homepage":
        product_reviews = product_reviews.filter(show_on_homepage=True)
    if username:
        testimonials = testimonials.filter(user__username=username)
        product_reviews = product_reviews.filter(user__username=username)

    testimonial_rows = testimonials.annotate(
        feed_source=Value(PLATFORM_SOURCE, output_field=CharField(max_length=32)),
        feed_review_type=Value(PLATFORM_REVIEW_TYPE, output_field=CharField(max_length=16)),
        feed_object_id=F("id"),
        feed_sort_at=F("created_at"),
        feed_priority=Value(100, output_field=IntegerField()),
    ).values_list(
        "feed_source",
        "feed_review_type",
        "feed_object_id",
        "feed_sort_at",
        "feed_priority",
    )

    product_rows = product_reviews.annotate(
        feed_source=Value(PRODUCT_SOURCE, output_field=CharField(max_length=32)),
        feed_review_type=Case(
            When(product_type="uslugi", then=Value(SERVICE_REVIEW_TYPE)),
            default=Value(PRODUCT_REVIEW_TYPE),
            output_field=CharField(max_length=16),
        ),
        feed_object_id=F("id"),
        feed_sort_at=Coalesce("published_at", "created_at", output_field=DateTimeField()),
        feed_priority=F("homepage_priority"),
    ).values_list(
        "feed_source",
        "feed_review_type",
        "feed_object_id",
        "feed_sort_at",
        "feed_priority",
    )

    rows = testimonial_rows.union(product_rows, all=True)
    if placement == "homepage":
        return rows.order_by("feed_priority", "-feed_sort_at", "-feed_object_id")
    return rows.order_by("-feed_sort_at", "-feed_object_id")


def _testimonial_queryset(ids):
    media_queryset = TestimonialMedia.objects.only(
        "id", "testimonial_id", "media_type", "image", "video_url", "video_file",
        "order", "created_at",
    ).order_by("order", "created_at")
    return (
        Testimonial.objects.filter(pk__in=ids)
        .select_related("user")
        .prefetch_related(Prefetch("media", queryset=media_queryset), "translations")
        .only(
            "id", "user_id", "user__id", "user__username", "user__avatar",
            "author_name", "author_avatar", "text", "rating", "created_at",
        )
    )


def _product_review_queryset(ids):
    from apps.catalog.models import Product, ProductImage, Service, ServiceImage

    media_queryset = ProductReviewMedia.objects.only(
        "id", "review_id", "media_type", "file", "order",
    ).order_by("order", "id")

    products = Product.objects.filter(
        slug=OuterRef("product_slug"),
        is_active=True,
    ).order_by("pk")
    product_images = ProductImage.objects.filter(
        product__slug=OuterRef("product_slug"),
        product__is_active=True,
    ).order_by("-is_main", "sort_order", "created_at", "pk")
    services = Service.objects.filter(
        slug=OuterRef("product_slug"),
        is_active=True,
    ).order_by("pk")
    service_images = ServiceImage.objects.filter(
        service__slug=OuterRef("product_slug"),
        service__is_active=True,
    ).order_by("-is_main", "sort_order", "created_at", "pk")

    def image_value(queryset, field_name):
        return Subquery(
            queryset.values(field_name)[:1],
            output_field=CharField(max_length=2000),
        )

    def subject_value(product_value, service_value):
        return Case(
            When(has_feed_media=True, then=Value(None)),
            When(product_type="uslugi", then=service_value),
            default=product_value,
            output_field=CharField(max_length=2000),
        )

    return (
        ProductReview.objects.filter(pk__in=ids)
        .select_related("user")
        .prefetch_related(Prefetch("media", queryset=media_queryset), "translations")
        .annotate(
            has_feed_media=Exists(
                ProductReviewMedia.objects.filter(review_id=OuterRef("pk"))
            ),
        )
        .annotate(
            subject_main_image_file=subject_value(
                image_value(products, "main_image_file"),
                image_value(services, "main_image_file"),
            ),
            subject_main_image_url=subject_value(
                image_value(products, "main_image"),
                image_value(services, "main_image"),
            ),
            subject_gallery_image_file=subject_value(
                image_value(product_images, "image_file"),
                image_value(service_images, "image_file"),
            ),
            subject_gallery_image_url=subject_value(
                image_value(product_images, "image_url"),
                image_value(service_images, "image_url"),
            ),
        )
        .only(
            "id", "user_id", "user__id", "user__username", "user__avatar",
            "product_type", "product_slug", "product_name", "author_name", "rating",
            "text", "status", "created_at", "updated_at", "homepage_priority",
            "admin_reply", "admin_replied_at",
        )
    )


def _catalog_subject_names(items, lang):
    """
    Название товара/услуги из каталога на языке запроса: product_name в отзыве — снимок
    на языке, на котором его оставили. Один запрос на тип товара, без N+1; для ru — снимок.
    """
    if not lang or lang == "ru":
        return {}
    from django.core.exceptions import FieldDoesNotExist

    from apps.catalog.models import Product, ProductTranslation, ServiceTranslation

    slugs_by_type = defaultdict(set)
    for item in items:
        if item.get("product_type") and item.get("product_slug"):
            slugs_by_type[item["product_type"]].add(item["product_slug"])
    domain_by_type = {
        str(getattr(rel.related_model, "_domain_product_type", "") or "").replace("-", "_"): rel.related_model
        for rel in Product._meta.related_objects
        if rel.one_to_one
    }
    names = {}
    for product_type, slugs in slugs_by_type.items():
        if product_type == "uslugi":
            rows = ServiceTranslation.objects.filter(locale=lang, service__slug__in=slugs).values_list("service__slug", "name")
        else:
            domain = domain_by_type.get(str(product_type).replace("-", "_"))
            try:
                translations_rel = domain._meta.get_field("translations") if domain is not None else None
            except FieldDoesNotExist:
                translations_rel = None
            if translations_rel is not None:
                fk = translations_rel.field.name
                rows = translations_rel.related_model.objects.filter(
                    locale=lang, **{f"{fk}__slug__in": slugs},
                ).values_list(f"{fk}__slug", "name")
            else:
                rows = ProductTranslation.objects.filter(locale=lang, product__slug__in=slugs).values_list("product__slug", "name")
        for slug, name in rows:
            if (name or "").strip():
                names[(product_type, slug)] = name.strip()
    return names


def serialize_review_feed_page(rows, *, request):
    """Load the two model types in bulk and normalize them into one API contract."""

    testimonial_ids = [row[2] for row in rows if row[0] == PLATFORM_SOURCE]
    product_review_ids = [row[2] for row in rows if row[0] == PRODUCT_SOURCE]

    testimonial_data = {
        item["id"]: item
        for item in TestimonialSerializer(
            _testimonial_queryset(testimonial_ids),
            many=True,
            context={"request": request},
        ).data
    }
    product_review_data = {
        item["id"]: item
        for item in ProductReviewSerializer(
            _product_review_queryset(product_review_ids),
            many=True,
            context={"request": request},
        ).data
    }

    lang = (getattr(request, "LANGUAGE_CODE", None) or "ru").split("-")[0]
    subject_names = _catalog_subject_names(product_review_data.values(), lang)

    result = []
    for source, review_type, object_id, sort_at, priority in rows:
        if source == PLATFORM_SOURCE:
            item = testimonial_data.get(object_id)
            if not item:
                continue
            media = [
                {
                    "id": media_item["id"],
                    "media_type": media_item["media_type"],
                    "image_url": media_item["image_url"],
                    "video_url": media_item["video_url"],
                    "video_file_url": media_item["video_file_url"],
                    "order": media_item["order"],
                }
                for media_item in item["media"]
            ]
            result.append({
                "uid": f"{PLATFORM_SOURCE}:{object_id}",
                "id": object_id,
                "source_type": PLATFORM_SOURCE,
                "review_type": review_type,
                "author_name": item["author_name"],
                "author_avatar_url": item["author_avatar_url"],
                "text": item["text"],
                "rating": item["rating"],
                "media": media,
                "created_at": sort_at,
                "user_id": item["user_id"],
                "user_username": item["user_username"],
                "product_type": None,
                "product_slug": None,
                "product_name": None,
                "subject_image_url": None,
                "homepage_priority": priority,
            })
            continue

        item = product_review_data.get(object_id)
        if not item:
            continue
        media = [
            {
                "id": media_item["id"],
                "media_type": "image" if media_item["media_type"] == "image" else "video_file",
                "image_url": media_item["url"] if media_item["media_type"] == "image" else None,
                "video_url": None,
                "video_file_url": media_item["url"] if media_item["media_type"] == "video" else None,
                "order": media_item["order"],
            }
            for media_item in item["media"]
        ]
        result.append({
            "uid": f"{PRODUCT_SOURCE}:{object_id}",
            "id": object_id,
            "source_type": PRODUCT_SOURCE,
            "review_type": review_type,
            "author_name": item["author_name"],
            "author_avatar_url": item["author_avatar_url"],
            "text": item["text"],
            "rating": item["rating"],
            "media": media,
            "created_at": sort_at,
            "user_id": item["user_id"],
            "user_username": item["user_username"],
            "product_type": item["product_type"],
            "product_slug": item["product_slug"],
            "product_name": subject_names.get((item["product_type"], item["product_slug"]), item["product_name"]),
            "subject_image_url": item["subject_image_url"] if not media else None,
            "homepage_priority": priority,
        })
    return ReviewFeedItemSerializer(result, many=True).data
