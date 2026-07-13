"""Celery tasks for recommendations (indexing, event logging)."""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


def _working_product_image_url(product):
    """Выбрать существующий storage-файл, не возвращая битый parsed URL."""
    from django.core.files.storage import default_storage
    from apps.catalog.signals import _get_path_from_storage_url, is_internal_storage_url

    main_file = getattr(product, "main_image_file", None)
    main_name = getattr(main_file, "name", "") or ""
    if main_name:
        try:
            if default_storage.exists(main_name):
                return main_file.url
        except Exception:
            pass

    main_url = str(getattr(product, "main_image", "") or "")
    if main_url:
        if not is_internal_storage_url(main_url):
            return main_url
        path = _get_path_from_storage_url(main_url)
        try:
            if path and default_storage.exists(path):
                return main_url
        except Exception:
            pass

    first_img = product.images.exclude(image_file="").first()
    image_file = getattr(first_img, "image_file", None) if first_img else None
    image_name = getattr(image_file, "name", "") or ""
    try:
        if image_name and default_storage.exists(image_name):
            return image_file.url
    except Exception:
        pass
    return ""


@shared_task(acks_late=False)
def index_product_vectors(product_ids=None, batch_size=100):
    """
    Index products into Qdrant.
    If product_ids is None, select products without vector_data or with last_synced < updated_at.
    """
    from apps.catalog.models import Product
    from django.db.models import Q, F
    from .models import ProductVector
    from .services.vector_engine import QdrantRecommendationEngine
    from .services.text_encoder import TextEncoder
    from .services.image_encoder import CLIPEncoder

    engine = QdrantRecommendationEngine()
    text_encoder = TextEncoder()
    image_encoder = CLIPEncoder()

    if product_ids is not None:
        queryset = (
            Product.objects.filter(id__in=product_ids)
            .exclude(
                Q(product_type__in=['clothing', 'shoes']) &
                (
                    Q(external_data__has_key='source_variant_id') |
                    Q(external_data__has_key='source_variant_slug')
                )
            )
            .select_related("category", "brand")
            .prefetch_related("images")
        )
        total_to_index = queryset.count()
    else:
        base_qs = (
            Product.objects.filter(is_available=True)
            .exclude(
                Q(product_type__in=['clothing', 'shoes']) &
                (
                    Q(external_data__has_key='source_variant_id') |
                    Q(external_data__has_key='source_variant_slug')
                )
            )
            .filter(
                Q(vector_data__isnull=True)
                | Q(vector_data__last_synced__isnull=True)
                | Q(vector_data__last_synced__lt=F("updated_at"))
            )
            .select_related("category", "brand")
            .prefetch_related("images")
        )
        total_to_index = base_qs.count()
        queryset = base_qs[:batch_size]

    total = 0
    errors = []
    for product in queryset:
        try:
            text = " ".join(
                filter(
                    None,
                    [
                        product.name,
                        product.description or "",
                        product.category.name if product.category else "",
                    ],
                )
            )
            text_vector = text_encoder.encode(text).tolist()
            image_vector = None
            img_url = _working_product_image_url(product)
            if img_url:
                try:
                    img_emb = image_encoder.encode_image_from_url(img_url)
                    if img_emb is not None:
                        image_vector = img_emb.tolist()
                except Exception as e:
                    logger.warning("Failed to encode image for product %s: %s", product.id, e)
            engine.upsert_product(
                product=product,
                text_vector=text_vector,
                image_vector=image_vector,
            )
            total += 1
        except Exception as e:
            errors.append({"product_id": product.id, "error": str(e)})
            logger.exception("Index product %s failed", product.id)

    return {
        "indexed": total,
        "errors": errors,
        "remaining": max(0, total_to_index - total),
    }


@shared_task(acks_late=False)
def sync_all_products_to_qdrant():
    """Ручная полная переиндексация. В регулярном расписании не используется."""
    from apps.catalog.models import Product
    from .models import ProductVector

    ProductVector.objects.update(last_synced=None)
    from django.db.models import Q
    base_qs = Product.objects.filter(is_available=True).exclude(
        Q(product_type__in=['clothing', 'shoes']) &
        (
            Q(external_data__has_key='source_variant_id') |
            Q(external_data__has_key='source_variant_slug')
        )
    )
    total = base_qs.count()
    batch_size = 25
    batches = (total // batch_size) + 1
    for offset in range(0, total, batch_size):
        ids = list(
            base_qs.values_list("id", flat=True)[offset : offset + batch_size]
        )
        index_product_vectors.delay(product_ids=ids)
    return {"batches": batches}


@shared_task(acks_late=False)
def sync_stale_products_to_qdrant(batch_size=25, max_products=200):
    """Ночная инкрементальная индексация только новых/изменённых товаров."""
    from django.core.cache import cache
    from django.db.models import F, Q
    from apps.catalog.models import Product

    lock_key = "recsys:sync-stale:scheduled"
    if not cache.add(lock_key, "1", timeout=60 * 60 * 6):
        return {"submitted": 0, "status": "already_scheduled"}

    ids = list(
        Product.objects.filter(is_available=True)
        .exclude(
            Q(product_type__in=["clothing", "shoes"])
            & (
                Q(external_data__has_key="source_variant_id")
                | Q(external_data__has_key="source_variant_slug")
            )
        )
        .filter(
            Q(vector_data__isnull=True)
            | Q(vector_data__last_synced__isnull=True)
            | Q(vector_data__last_synced__lt=F("updated_at"))
        )
        .order_by("updated_at")
        .values_list("id", flat=True)[:max_products]
    )
    for offset in range(0, len(ids), batch_size):
        index_product_vectors.apply_async(
            kwargs={"product_ids": ids[offset : offset + batch_size]},
            priority=3,
        )
    return {
        "submitted": len(ids),
        "batches": (len(ids) + batch_size - 1) // batch_size,
        "status": "scheduled",
    }


@shared_task
def log_recommendation_event(
    event_type,
    source_product_id,
    recommended_ids,
    algorithm,
    session_id="",
):
    """Create RecommendationEvent records for each recommended product."""
    from .models import RecommendationEvent

    for position, rec_id in enumerate(recommended_ids, 1):
        RecommendationEvent.objects.create(
            event_type=event_type,
            source_product_id=source_product_id,
            recommended_product_id=rec_id,
            algorithm=algorithm,
            position=position,
            session_id=session_id or "",
        )


@shared_task
def cleanup_temp_images():
    """
    Delete temporary images older than 1 hour from the temp/ directory.
    Uses default_storage which works with both local and S3 endpoints.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.core.files.storage import default_storage
    import os

    try:
        # For S3, directories might not be explicitly returned but objects with "temp/" prefix exist
        # default_storage listdir returns (dirs, files)
        try:
            _, files = default_storage.listdir("temp")
        except FileNotFoundError:
            # Local dev without temp dir created yet
            return {"deleted": 0}

        deleted_count = 0
        now = timezone.now()
        threshold = now - timedelta(hours=1)

        for filename in files:
            file_path = f"temp/{filename}"
            try:
                # Get modified time; works differently per storage backend but generally returns datetime
                modified_time = default_storage.get_modified_time(file_path)
                
                # Make timezone aware if it's naive
                if timezone.is_naive(modified_time):
                    modified_time = timezone.make_aware(modified_time)
                
                if modified_time < threshold:
                    default_storage.delete(file_path)
                    deleted_count += 1
            except Exception as e:
                logger.error("Failed to delete temp file %s: %s", file_path, e)
                
        return {"deleted": deleted_count}
    except Exception as e:
        logger.error("Error running cleanup_temp_images: %s", e)
        return {"error": str(e)}
