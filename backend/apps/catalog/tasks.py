"""Celery tasks for catalog refresh, source checks, pricing and media."""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
import logging

from apps.catalog.services import MedicineMediaEnricher

logger = logging.getLogger(__name__)


@shared_task(
    name="catalog.refresh_medicine_market_check",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_medicine_market_check_task(check_id: int) -> dict:
    """Refresh one user-requested medicine reference price and its equivalents."""

    from apps.catalog.services.medicine_market_check import MedicineMarketCheckService

    return MedicineMarketCheckService().run(check_id)


@shared_task(
    name="catalog.refresh_supplement_market_check",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_supplement_market_check_task(check_id: int) -> dict:
    """Refresh one user-requested supplement reference price."""

    from apps.catalog.services.supplement_market_check import (
        SupplementMarketCheckService,
    )

    return SupplementMarketCheckService().run(check_id)


@shared_task(
    bind=True,
    name="catalog.discover_supplement_stock_offer",
    soft_time_limit=55,
    time_limit=60,
    acks_late=True,
    max_retries=2,
    default_retry_delay=60,
)
def discover_supplement_stock_offer_task(self, supplement_id: int) -> dict:
    """Discover one supplement seller identity independently of reference price."""

    from apps.catalog.models import SupplementProduct
    from apps.catalog.services.supplement_stock_discovery import (
        SupplementStockDiscoveryError,
        SupplementStockDiscoveryService,
    )

    supplement = (
        SupplementProduct.objects.select_related("base_product")
        .filter(pk=supplement_id, is_active=True)
        .first()
    )
    if supplement is None:
        return {"status": "missing", "supplement_id": supplement_id}

    try:
        result = SupplementStockDiscoveryService().discover(supplement)
    except SupplementStockDiscoveryError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        logger.warning(
            "supplement_stock_discovery_task_failed",
            extra={
                "supplement_id": supplement_id,
                "product_id": supplement.base_product_id,
                "error_code": exc.code,
                "retryable": exc.retryable,
            },
        )
        return {
            "status": "error",
            "supplement_id": supplement_id,
            "error_code": exc.code,
            "retryable": exc.retryable,
        }

    return {
        "status": result.status,
        "supplement_id": supplement_id,
        "offer_id": result.offer.pk if result.offer is not None else None,
    }


@shared_task(
    name="catalog.refresh_product_card_source",
    soft_time_limit=100,
    time_limit=120,
    acks_late=True,
)
def refresh_product_card_source_task(product_id: int, lock_token: str) -> dict:
    """Refresh one parsed card without invoking the content-import pipeline."""

    from apps.catalog.services.product_card_source_refresh import (
        ProductCardSourceRefreshService,
    )

    service = ProductCardSourceRefreshService()
    try:
        return service.run(product_id)
    finally:
        service.release_lock(product_id, lock_token)


@shared_task
def refresh_stock() -> str:
    """Обновляет данные о наличии товаров (заглушка)."""
    return "stock refreshed"


@shared_task
def refresh_prices() -> str:
    """Обновляет цены на товары с учетом наценок/акций (заглушка)."""
    return "prices refreshed"


# Задачи для системы ценообразования
@shared_task(name='currency.update_rates')
def update_currency_rates():
    """Периодическое обновление курсов валют."""
    try:
        logger.info("Starting currency rates update...")
        
        from .utils.currency_service import CurrencyRateService
        service = CurrencyRateService()
        success, message = service.update_rates()
        
        if success:
            logger.info(f"Currency rates updated successfully: {message}")
            return {'status': 'success', 'message': message}
        else:
            logger.error(f"Currency rates update failed: {message}")
            return {'status': 'error', 'message': message}
            
    except Exception as e:
        logger.error(f"Exception in currency rates update: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='currency.update_product_prices')
def update_product_prices_batch(product_type=None, batch_size=100):
    """Периодическое обновление цен товаров."""
    try:
        logger.info(f"Starting product prices update for type: {product_type}")
        
        # Вызываем management команду
        call_command(
            'update_product_prices',
            product_type=product_type,
            batch_size=batch_size,
            force_update_rates=False  # Не обновляем курсы каждый раз
        )
        
        logger.info("Product prices update completed successfully")
        return {'status': 'success', 'message': 'Product prices updated'}
        
    except Exception as e:
        logger.error(f"Exception in product prices update: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='currency.refresh_margin_snapshots')
def refresh_currency_margin_snapshots_task():
    """Применяет актуальные маржи валютных пар к сохранённым конвертированным ценам."""
    from .currency_price_snapshots import refresh_currency_margin_snapshots

    return refresh_currency_margin_snapshots()


@shared_task(name='currency.refresh_usdt_price_snapshots')
def refresh_usdt_price_snapshots_task():
    """Пересчитывает сохранённые цены после изменения глобальной USDT-наценки."""
    from .currency_price_snapshots import refresh_usdt_price_snapshots

    return refresh_usdt_price_snapshots()


@shared_task(name='currency.cleanup_old_logs')
def cleanup_old_currency_logs(days_to_keep=30):
    """Очистка старых логов обновления курсов."""
    try:
        from django.utils import timezone
        from datetime import timedelta
        from .currency_models import CurrencyUpdateLog
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        deleted_count = CurrencyUpdateLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old currency update logs")
        return {
            'status': 'success', 
            'deleted_count': deleted_count,
            'message': f'Cleaned up {deleted_count} old logs'
        }
        
    except Exception as e:
        logger.error(f"Exception in currency logs cleanup: {str(e)}")
        return {'status': 'error', 'message': str(e)}


def _normalize_media_path(path: str) -> str:
    """Нормализация пути для сравнения: убрать лишние слэши, префиксы dev/prod, привести к единому виду."""
    if not path or not isinstance(path, str):
        return ""
    
    # Убираем /media/ если есть (из URL)
    if path.startswith("/media/"):
        path = path[len("/media/"):]
        
    p = path.strip("/").replace("//", "/")
    
    # Убираем префикс R2 если он там есть
    from django.conf import settings
    prefix = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    if prefix and p.startswith(prefix + "/"):
        p = p[len(prefix) + 1:]
    elif prefix and p == prefix:
        return ""
        
    return p


def _collect_db_media_paths():
    """
    Собрать все пути к медиа-файлам из БД.
    Динамически обходит все модели всех приложений, находит FileField/ImageField,
    а также URLField, и собирает пути. Это защищает от пропуска новых моделей/полей.
    """
    from django.apps import apps
    from django.db.models import FileField, ImageField, URLField
    from urllib.parse import urlparse

    paths = set()
    seen = set()  # (model_label, field_name) для логирования

    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, (FileField, ImageField, URLField)):
                continue
            key = (model._meta.label, field.name)
            if key in seen:
                continue
            seen.add(key)
            try:
                manager = getattr(model, "_base_manager", model.objects)
                for obj in manager.only(field.name).iterator(chunk_size=500):
                    val = getattr(obj, field.name, None)
                    if not val:
                        continue
                    if isinstance(field, (FileField, ImageField)):
                        if getattr(val, "name", None):
                            normalized = _normalize_media_path(val.name)
                            if normalized:
                                paths.add(normalized)
                    elif isinstance(field, URLField):
                        if isinstance(val, str) and val.strip():
                            parsed = urlparse(val)
                            path = parsed.path
                            normalized = _normalize_media_path(path)
                            if normalized:
                                paths.add(normalized)
            except Exception as e:
                logger.warning("cleanup_orphaned_media: skip %s.%s: %s", model._meta.label, field.name, e)
    return paths


def _list_storage_files(storage, path=""):
    """Рекурсивно собрать все ключи файлов в хранилище."""
    collected = set()
    try:
        dirs, files = storage.listdir(path)
        for f in files:
            full = f"{path}/{f}" if path else f
            collected.add(_normalize_media_path(full))
        for d in dirs:
            prefix = f"{path}/{d}" if path else d
            collected.update(_list_storage_files(storage, prefix))
    except Exception:
        pass
    return collected


# Префиксы путей, которые НИКОГДА не удалять (AI-обработка, кэш, временные файлы, аватарки).
# Файлы здесь не привязаны к моделям Django или привязаны, но могут не попасть в _collect_db_media_paths.
_PROTECTED_STORAGE_PREFIXES = (
    "products/original/",
    "products/processed/",
    "products/thumbs/",
    "temp/",
    "avatars/",  # аватарки пользователей (users.User.avatar)
    "testimonials/",  # аватарки авторов отзывов (feedback.Testimonial.author_avatar)
)

# Известные корневые директории медиа
_KNOWN_ROOT_DIRS = (
    "products/", "temp/", "avatars/", "testimonials/", "marketing/", "services/"
)

# Префиксы других окружений — не удалять при очистке.
# На проде (R2_PREFIX="") listdir возвращает весь бакет, включая dev/.
# Без этой защиты prod-задача удаляла бы медиа из dev/.
_OTHER_ENV_PREFIXES = ("dev/", "staging/", "test/", "local/")


def _is_protected_path(path: str) -> bool:
    """Проверить, что путь защищён от удаления."""
    if not path:
        return True
    
    # Если путь начинается с папки, которая не является известной (например, префикс разработчика `misha/`),
    # мы всегда защищаем этот путь, чтобы продакшен скрипт не удалял локальные файлы.
    has_known_root = any(path.startswith(r) for r in _KNOWN_ROOT_DIRS)
    if not has_known_root and "/" in path:
        return True

    normalized = _normalize_media_path(path)
    
    for prefix in _PROTECTED_STORAGE_PREFIXES:
        if normalized.startswith(prefix) or path.startswith(prefix):
            return True
            
    # Не удалять файлы из других окружений (dev/, staging/ и т.д.)
    for prefix in _OTHER_ENV_PREFIXES:
        if normalized.startswith(prefix) or path.startswith(prefix):
            return True
            
    return False


@shared_task(name="catalog.cleanup_orphaned_media")
def cleanup_orphaned_media():
    """
    Удаление файлов из R2/локального хранилища, которых нет в БД.
    Не удаляет: защищённые префиксы (AI, temp), пути других окружений (dev/, staging/).
    На проде (R2_PREFIX="") listdir возвращает весь бакет — без защиты dev/ файлы удалялись бы.
    """
    from django.conf import settings
    if getattr(settings, 'DEBUG', False):
        logger.info("cleanup_orphaned_media skipped: DEBUG=True. (Prevents local celery from wiping shared media across developers using the same R2 prefix)")
        return {"status": "skipped", "message": "Disabled in DEBUG mode"}

    from django.core.files.storage import default_storage

    try:
        db_paths = _collect_db_media_paths()
        try:
            storage_paths = _list_storage_files(default_storage)
        except Exception as e:
            logger.warning("Could not list storage files (e.g. not using R2): %s", e)
            return {"status": "skipped", "message": "Storage listing not supported", "deleted": 0}

        # Только те файлы в storage, которых нет в БД
        orphaned = storage_paths - db_paths
        # Исключаем защищённые пути (AI, temp, avatars) и пути других окружений (dev/, staging/)
        to_delete = [p for p in orphaned if not _is_protected_path(p)]

        logger.info(
            "cleanup_orphaned_media: db_paths=%s, storage_paths=%s, orphaned=%s, protected_excluded=%s, to_delete=%s",
            len(db_paths),
            len(storage_paths),
            len(orphaned),
            len(orphaned) - len(to_delete),
            len(to_delete),
        )
        if to_delete and len(to_delete) <= 20:
            logger.info("cleanup_orphaned_media: will delete paths: %s", to_delete)
        elif to_delete:
            logger.info("cleanup_orphaned_media: will delete first 10 paths: %s", to_delete[:10])

        # Предохранитель (инцидент 2026-06-14): стек с ПУСТОЙ БД + общий R2-бакет
        # стёр весь каталог, т.к. "осиротевшим" оказалось всё. Не удаляем, если БД
        # подозрительно пуста или удаление затронуло бы слишком большую долю хранилища.
        MIN_DB_PATHS = 100
        if len(db_paths) < MIN_DB_PATHS:
            logger.error(
                "cleanup_orphaned_media ABORTED: db_paths=%s < %s — похоже на пустую/битую БД, удаление пропущено",
                len(db_paths), MIN_DB_PATHS,
            )
            return {"status": "aborted", "reason": "db_paths_too_low", "db_paths": len(db_paths), "deleted": 0}
        if storage_paths and len(to_delete) > len(storage_paths) // 2:
            logger.error(
                "cleanup_orphaned_media ABORTED: to_delete=%s > 50%% storage=%s — защита от массового удаления",
                len(to_delete), len(storage_paths),
            )
            return {"status": "aborted", "reason": "mass_deletion_guard", "to_delete": len(to_delete), "storage": len(storage_paths), "deleted": 0}

        deleted = 0
        for path in to_delete:
            try:
                # default_storage уже настроен на R2_PREFIX через location
                # поэтому удаление path удалит именно то, что нужно.
                default_storage.delete(path)
                deleted += 1
            except Exception as e:
                logger.warning("Failed to delete orphaned file %s: %s", path, e)
        logger.info("cleanup_orphaned_media: deleted %s orphaned files", deleted)
        return {"status": "success", "deleted": deleted}
    except Exception as e:
        logger.exception("cleanup_orphaned_media failed: %s", e)
        return {"status": "error", "message": str(e), "deleted": 0}


@shared_task(name='currency.health_check')
def currency_system_health_check():
    """Проверка здоровья системы валют."""
    try:
        from .models import Product
        from .currency_models import CurrencyRate
        
        # Проверяем наличие активных курсов
        active_rates = CurrencyRate.objects.filter(is_active=True).count()
        
        # Проверяем товары без цен
        products_without_prices = Product.objects.filter(
            price__isnull=True
        ).count()
        
        # Проверяем товары без конвертированных цен
        products_without_converted = Product.objects.filter(
            price__isnull=False,
            converted_price_rub__isnull=True
        ).count()
        
        health_data = {
            'active_rates': active_rates,
            'products_without_prices': products_without_prices,
            'products_without_converted': products_without_converted,
            'status': 'healthy'
        }
        
        # Если есть проблемы, меняем статус
        if active_rates == 0 or products_without_prices > 1000:
            health_data['status'] = 'warning'
        
        logger.info(f"Currency system health check: {health_data}")
        return health_data
        
    except Exception as e:
        logger.error(f"Exception in currency health check: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task(
    name="catalog.enrich_medicine_media",
    bind=True, max_retries=2, default_retry_delay=300,
)
def enrich_medicine_media(
    self,
    product_ids: list[int] | None = None,
    max_images_per_product: int = 3,
    ignore_cache: bool = False,
    model_name: str = 'MedicineProduct',
    requested_by_user_id: int | None = None,
) -> dict:
    """
    Ручной поиск кандидатов медиа для MedicineProduct и SupplementProduct.

    Без явно переданных ``product_ids`` задача является безопасным no-op. Найденные
    файлы попадают только в очередь модерации и не изменяют товарную галерею.
    """
    try:
        from django.apps import apps
        from apps.catalog.models import MediaEnrichmentStatus

        if not product_ids or not requested_by_user_id:
            logger.warning(
                "Rejected media enrichment without an explicit manual product selection "
                "and staff initiator."
            )
            return {
                "status": "manual_selection_required",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        from django.contrib.auth import get_user_model

        requested_by = get_user_model().objects.filter(
            pk=requested_by_user_id,
            is_active=True,
            is_staff=True,
        ).first()
        if requested_by is None:
            logger.warning(
                "Rejected media enrichment with invalid staff initiator id=%s.",
                requested_by_user_id,
            )
            return {
                "status": "manual_selection_required",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        allowed_models = {"MedicineProduct", "SupplementProduct"}
        if model_name not in allowed_models:
            return {
                "status": "error",
                "message": "unsupported_model",
                "products_processed": 0,
                "candidates_staged": 0,
                "images_added": 0,
                "errors": 0,
                "skipped": 0,
                "no_results": 0,
            }

        ProductModel = apps.get_model('catalog', model_name)
        queryset = ProductModel.objects.filter(id__in=product_ids)
        queryset.update(
            media_enrichment_status=MediaEnrichmentStatus.PROCESSING,
            media_enrichment_error=None,
        )

        enricher = MedicineMediaEnricher()

        products_processed = 0
        candidates_staged = 0
        errors = 0
        skipped = 0
        no_results = 0

        for product in queryset:
            products_processed += 1
            try:
                staged = enricher.enrich(
                    product,
                    max_images_per_product,
                    ignore_cache=ignore_cache,
                    requested_by=requested_by,
                )
                candidates_staged += staged
                if product.media_enrichment_status == MediaEnrichmentStatus.FAILED:
                    errors += 1
                elif staged == 0:
                    from apps.catalog.services.medicine_media_enricher import (
                        MEDIA_ENRICHMENT_MAX_IMAGES,
                        MEDIA_ENRICHMENT_RECENT_NO_RESULT,
                    )

                    if product.media_enrichment_error in {
                        MEDIA_ENRICHMENT_MAX_IMAGES,
                        MEDIA_ENRICHMENT_RECENT_NO_RESULT,
                    }:
                        skipped += 1
                    else:
                        no_results += 1
            except Exception as e:
                logger.error("Failed to enrich media for product %s (%s): %s", product.id, model_name, e)
                product.media_enrichment_status = MediaEnrichmentStatus.FAILED
                product.media_enrichment_error = str(e)
                product.save(update_fields=['media_enrichment_status', 'media_enrichment_error'])
                errors += 1

        if errors == products_processed and products_processed:
            result_status = "error"
        elif errors:
            result_status = "partial"
        elif candidates_staged == 0:
            result_status = "no_changes"
        else:
            result_status = "success"

        return {
            "status": result_status,
            "products_processed": products_processed,
            "candidates_staged": candidates_staged,
            "images_added": 0,
            "errors": errors,
            "skipped": skipped,
            "no_results": no_results,
        }
    except Exception as e:
        logger.exception("enrich_medicine_media failed: %s", e)
        # Only retry if it's not a direct caller issue
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {"status": "error", "message": str(e)}


@shared_task(
    name="catalog.sync_ikea_products",
    bind=True, max_retries=3, default_retry_delay=300,
)
def sync_ikea_product_task(self, item_codes: list[str]) -> dict:
    """Задача: получение данных о товарах IKEA по артикулам."""
    from apps.catalog.services import IkeaService
    
    service = IkeaService()
    items = service.fetch_items(item_codes)
    
    processed = 0
    errors = 0
    
    for item in items:
        try:
            service.upsert_furniture_product(item)
            processed += 1
        except Exception as e:
            logger.error(f"Error upserting IKEA product: {str(e)}")
            errors += 1
            
    return {
        "status": "success",
        "processed": processed,
        "errors": errors,
        "total": len(item_codes)
    }
