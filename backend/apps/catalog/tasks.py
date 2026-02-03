"""Задачи Celery для каталога: обновление цен, остатков и курсов валют.

В MVP-версии реализованы заглушки, которые позже будут интегрированы с парсером.
"""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command
import logging

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
        
        from .services.currency_service import CurrencyRateService
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


def _collect_db_media_paths():
    """Собрать все пути к медиа-файлам из БД (все модели с FileField/ImageField)."""
    from django.db.models import FileField, ImageField

    paths = set()
    models_to_scan = [
        ("apps.catalog", "Product", "main_image_file"),
        ("apps.catalog", "ProductImage", "image_file"),
        ("apps.catalog", "Category", "card_media"),
        ("apps.catalog", "Brand", "card_media"),
        ("apps.catalog", "ClothingProduct", "main_image_file"),
        ("apps.catalog", "ClothingProductImage", "image_file"),
        ("apps.catalog", "ClothingVariant", "main_image_file"),
        ("apps.catalog", "ClothingVariantImage", "image_file"),
        ("apps.catalog", "ShoeProduct", "main_image_file"),
        ("apps.catalog", "ShoeProductImage", "image_file"),
        ("apps.catalog", "ShoeVariant", "main_image_file"),
        ("apps.catalog", "ShoeVariantImage", "image_file"),
        ("apps.catalog", "JewelryProduct", "main_image_file"),
        ("apps.catalog", "JewelryProductImage", "image_file"),
        ("apps.catalog", "JewelryVariant", "main_image_file"),
        ("apps.catalog", "JewelryVariantImage", "image_file"),
        ("apps.catalog", "ElectronicsProduct", "main_image_file"),
        ("apps.catalog", "ElectronicsProductImage", "image_file"),
        ("apps.catalog", "FurnitureProduct", "main_image_file"),
        ("apps.catalog", "FurnitureVariant", "main_image_file"),
        ("apps.catalog", "FurnitureVariantImage", "image_file"),
        ("apps.catalog", "BookVariantImage", "image_file"),
        ("apps.catalog", "BannerMedia", "image"),
        ("apps.catalog", "BannerMedia", "video_file"),
        ("apps.catalog", "BannerMedia", "gif_file"),
        ("apps.users", "User", "avatar"),
        ("apps.feedback", "Testimonial", "author_avatar"),
        ("apps.feedback", "TestimonialMedia", "image"),
        ("apps.feedback", "TestimonialMedia", "video_file"),
    ]
    from django.apps import apps
    for app_label, model_name, field_name in models_to_scan:
        try:
            model = apps.get_model(app_label, model_name)
            field = model._meta.get_field(field_name)
            if isinstance(field, (FileField, ImageField)):
                for obj in model.objects.only(field_name).iterator():
                    val = getattr(obj, field_name)
                    if val and getattr(val, "name", None):
                        paths.add(val.name)
        except (LookupError, Exception):
            continue
    return paths


def _list_storage_files(storage, path=""):
    """Рекурсивно собрать все ключи файлов в хранилище."""
    collected = set()
    try:
        dirs, files = storage.listdir(path)
        for f in files:
            full = f"{path}/{f}" if path else f
            collected.add(full)
        for d in dirs:
            prefix = f"{path}/{d}" if path else d
            collected.update(_list_storage_files(storage, prefix))
    except Exception:
        pass
    return collected


@shared_task(name="catalog.cleanup_orphaned_media")
def cleanup_orphaned_media():
    """Удаление файлов из R2/локального хранилища, которых нет в БД."""
    from django.core.files.storage import default_storage

    try:
        db_paths = _collect_db_media_paths()
        try:
            storage_paths = _list_storage_files(default_storage)
        except Exception as e:
            logger.warning("Could not list storage files (e.g. not using R2): %s", e)
            return {"status": "skipped", "message": "Storage listing not supported", "deleted": 0}
        orphaned = storage_paths - db_paths
        deleted = 0
        for path in orphaned:
            try:
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

