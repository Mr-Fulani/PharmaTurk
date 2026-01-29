"""Management команда для обновления цен товаров в разных валютах."""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
import logging
from apps.catalog.models import Product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обновляет цены товаров в разных валютах с учетом маржи'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--product-id',
            type=int,
            help='ID конкретного товара для обновления'
        )
        parser.add_argument(
            '--product-type',
            type=str,
            help='Тип товаров для обновления (medicines, supplements, etc.)'
        )
        parser.add_argument(
            '--currency',
            type=str,
            default='RUB',
            help='Базовая валюта для обновления (по умолчанию RUB)'
        )
        parser.add_argument(
            '--force-update-rates',
            action='store_true',
            help='Принудительно обновить курсы валют перед конвертацией'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Размер пакета для обработки (по умолчанию 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет обновлено без реальных изменений'
        )
    
    def handle(self, *args, **options):
        product_id = options.get('product_id')
        product_type = options.get('product_type')
        currency = options.get('currency')
        force_update_rates = options.get('force_update_rates')
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')
        
        self.stdout.write(self.style.SUCCESS('Начинаю обновление цен товаров...'))
        
        # Обновляем курсы валют если нужно
        if force_update_rates:
            self.stdout.write(self.style.WARNING('Обновление курсов валют пропущено - используйте отдельную команду для обновления курсов'))
        
        # Получаем queryset товаров для обновления
        queryset = self._get_products_queryset(product_id, product_type)
        
        if not queryset.exists():
            self.stdout.write(self.style.WARNING('Товары для обновления не найдены'))
            return
        
        total_count = queryset.count()
        self.stdout.write(f'Найдено товаров для обновления: {total_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - изменения не будут сохранены'))
        
        # Обрабатываем товары пачками
        processed = 0
        errors = 0
        
        for batch_start in range(0, total_count, batch_size):
            batch_end = min(batch_start + batch_size, total_count)
            batch = queryset[batch_start:batch_end]
            
            for product in batch:
                try:
                    if not dry_run:
                        self._update_product_prices(product, currency)
                    else:
                        self._preview_price_update(product, currency)
                    
                    processed += 1
                    
                    if processed % 10 == 0:
                        self.stdout.write(f'Обработано: {processed}/{total_count}')
                
                except Exception as e:
                    errors += 1
                    logger.error(f"Error updating product {product.id}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'Ошибка обновления товара {product.id}: {str(e)}')
                    )
        
        # Выводим результаты
        self.stdout.write(self.style.SUCCESS(
            f'Завершено! Обработано: {processed}, ошибок: {errors}'
        ))
        
        if errors > 0:
            self.stdout.write(self.style.WARNING(
                f'Процент ошибок: {errors/processed*100:.2f}%'
            ))
    
    def _get_products_queryset(self, product_id=None, product_type=None):
        """Получает queryset товаров для обновления."""
        queryset = Product.objects.filter(
            price__isnull=False,
            currency__isnull=False,
            is_active=True
        )
        
        if product_id:
            queryset = queryset.filter(id=product_id)
        
        if product_type:
            queryset = queryset.filter(product_type=product_type)
        
        return queryset.order_by('id')
    
    def _update_product_prices(self, product, target_currency):
        """Обновляет цены для конкретного товара."""
        product.update_currency_prices([target_currency])
    
    def _preview_price_update(self, product, target_currency):
        """Предпросмотр обновления цен товара."""
        try:
            current_prices = product.get_all_prices()
            current_price = product.get_price_in_currency(target_currency)
            
            self.stdout.write(
                f'Товар #{product.id}: {product.name[:50]}...'
            )
            self.stdout.write(f'  Базовая цена: {product.price} {product.currency}')
            
            if current_price:
                self.stdout.write(f'  Текущая цена в {target_currency}: {current_price}')
            else:
                self.stdout.write(f'  Цена в {target_currency}: не рассчитана')
            
            if current_prices:
                self.stdout.write(f'  Доступные цены: {list(current_prices.keys())}')
            
        except Exception as e:
            self.stdout.write(f'  Ошибка получения данных: {str(e)}')
