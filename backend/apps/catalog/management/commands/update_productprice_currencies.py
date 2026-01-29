"""Команда для обновления конвертированных цен в таблице ProductPrice."""

from django.core.management.base import BaseCommand
from decimal import Decimal
import logging
from apps.catalog.currency_models import ProductPrice
from apps.catalog.utils.currency_converter import currency_converter

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обновляет конвертированные цены в таблице ProductPrice'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Размер пакета для обработки (по умолчанию 50)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет обновлено без реальных изменений'
        )
    
    def handle(self, *args, **options):
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')
        
        self.stdout.write(self.style.SUCCESS('Начинаю обновление цен в ProductPrice...'))
        
        # Получаем все записи ProductPrice
        queryset = ProductPrice.objects.all().select_related('product')
        total_count = queryset.count()
        
        self.stdout.write(f'Найдено записей для обновления: {total_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - изменения не будут сохранены'))
        
        processed = 0
        errors = 0
        updated = 0
        
        for price_info in queryset.iterator(chunk_size=batch_size):
            try:
                if not price_info.base_price or not price_info.base_currency:
                    processed += 1
                    continue
                
                # Конвертируем во все валюты
                target_currencies = ['RUB', 'USD', 'KZT', 'EUR', 'TRY']
                results = currency_converter.convert_to_multiple_currencies(
                    price_info.base_price,
                    price_info.base_currency,
                    target_currencies,
                    apply_margin=True
                )
                
                # Обновляем цены
                has_updates = False
                
                if 'RUB' in results and results['RUB']:
                    price_info.rub_price = results['RUB']['converted_price']
                    price_info.rub_price_with_margin = results['RUB']['price_with_margin']
                    has_updates = True
                
                if 'USD' in results and results['USD']:
                    price_info.usd_price = results['USD']['converted_price']
                    price_info.usd_price_with_margin = results['USD']['price_with_margin']
                    has_updates = True
                
                if 'KZT' in results and results['KZT']:
                    price_info.kzt_price = results['KZT']['converted_price']
                    price_info.kzt_price_with_margin = results['KZT']['price_with_margin']
                    has_updates = True
                
                if 'EUR' in results and results['EUR']:
                    price_info.eur_price = results['EUR']['converted_price']
                    price_info.eur_price_with_margin = results['EUR']['price_with_margin']
                    has_updates = True
                
                if 'TRY' in results and results['TRY']:
                    price_info.try_price = results['TRY']['converted_price']
                    price_info.try_price_with_margin = results['TRY']['price_with_margin']
                    has_updates = True
                
                if has_updates and not dry_run:
                    price_info.save()
                    updated += 1
                
                processed += 1
                
                if processed % 10 == 0:
                    self.stdout.write(f'Обработано: {processed}/{total_count}')
            
            except Exception as e:
                errors += 1
                logger.error(f"Error updating ProductPrice {price_info.id}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f'Ошибка обновления ProductPrice {price_info.id}: {str(e)}')
                )
        
        # Выводим результаты
        self.stdout.write(self.style.SUCCESS(
            f'Завершено! Обработано: {processed}, обновлено: {updated}, ошибок: {errors}'
        ))
        
        if errors > 0:
            self.stdout.write(self.style.WARNING(
                f'Процент ошибок: {errors/processed*100:.2f}%'
            ))
