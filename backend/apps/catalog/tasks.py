"""Задачи Celery для каталога: обновление цен, остатков и курсов валют.

В MVP-версии реализованы заглушки, которые позже будут интегрированы с парсером.
"""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
from django.db.models import Count
import logging

from apps.catalog.models import MedicineProduct
from apps.catalog.services import MedicineMediaEnricher

logger = logging.getLogger(__name__)


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
    "products/parsed/",  # файлы, скачанные парсерами
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
) -> dict:
    """
    Обогащение медиа для MedicineProduct.
    - product_ids=None  → все товары с медиа меньше max_images_per_product
    - product_ids=[...] → только указанные товары
    """
    try:
        queryset = MedicineProduct.objects.annotate(
            gallery_images_count=Count('gallery_images')
        ).filter(gallery_images_count__lt=max_images_per_product)
        
        if product_ids:
            queryset = queryset.filter(id__in=product_ids)
            
        enricher = MedicineMediaEnricher()
        
        products_processed = 0
        images_added = 0
        errors = 0
        
        for product in queryset.iterator():
            try:
                added = enricher.enrich(product, max_images_per_product)
                products_processed += 1
                images_added += added
            except Exception as e:
                logger.error("Failed to enrich media for product %s: %s", product.id, e)
                errors += 1
                
        return {
            "status": "success",
            "products_processed": products_processed,
            "images_added": images_added,
            "errors": errors,
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

