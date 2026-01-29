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

