"""Management команда для обновления курсов валют."""

from django.core.management.base import BaseCommand
import requests
from decimal import Decimal
import logging
from apps.catalog.currency_models import CurrencyRate, CurrencyUpdateLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обновление курсов валют из внешних источников'

    def handle(self, *args, **options):
        self.stdout.write('Начинаю обновление курсов валют...')
        
        # Обновляем курсы из ЦБ РФ
        self.update_cbr_rates()
        
        # Обновляем курсы из Нацбанка КЗ  
        self.update_nbk_rates()
        
        self.stdout.write(self.style.SUCCESS('Обновление курсов завершено!'))

    def update_cbr_rates(self):
        """Обновление курсов из Центробанка РФ."""
        try:
            response = requests.get('https://www.cbr-xml-daily.ru/daily_json.js', timeout=30)
            response.raise_for_status()
            data = response.json()
            
            updated_count = 0
            
            # Обрабатываем основные валюты
            for currency_data in data['Valute'].values():
                code = currency_data['CharCode']
                if code in ['USD', 'EUR', 'TRY', 'KZT']:
                    value = Decimal(str(currency_data['Value'])) / Decimal(str(currency_data['Nominal']))
                    
                    # Сохраняем курс к рублю
                    rate, created = CurrencyRate.objects.update_or_create(
                        from_currency=code,
                        to_currency='RUB',
                        defaults={
                            'rate': value,
                            'source': 'centralbank_rf',
                            'is_active': True
                        }
                    )
                    
                    if not created:
                        rate.rate = value
                        rate.source = 'centralbank_rf'
                        rate.save()
                    
                    updated_count += 1
                    
                    # Создаем обратный курс
                    reverse_rate = Decimal('1') / value
                    CurrencyRate.objects.update_or_create(
                        from_currency='RUB',
                        to_currency=code,
                        defaults={
                            'rate': reverse_rate,
                            'source': 'centralbank_rf',
                            'is_active': True
                        }
                    )
            
            # Логируем успешное обновление
            CurrencyUpdateLog.objects.create(
                source='centralbank_rf',
                success=True,
                rates_updated=updated_count
            )
            
            self.stdout.write(f'ЦБ РФ: Обновлено {updated_count} курсов')
            
        except Exception as e:
            logger.error(f"Ошибка обновления ЦБ РФ: {str(e)}")
            CurrencyUpdateLog.objects.create(
                source='centralbank_rf',
                success=False,
                rates_updated=0,
                error_message=str(e)
            )
            self.stdout.write(self.style.ERROR(f'Ошибка ЦБ РФ: {str(e)}'))

    def update_nbk_rates(self):
        """Обновление курсов из Нацбанка Казахстана."""
        try:
            response = requests.get('https://nationalbank.kz/rss/rates_all.xml', timeout=30)
            response.raise_for_status()
            
            from xml.etree import ElementTree as ET
            root = ET.fromstring(response.text)
            
            updated_count = 0
            
            for item in root.findall('.//item'):
                title = item.find('title').text
                description = item.find('description').text
                
                if title in ['USD', 'EUR', 'RUB', 'TRY']:
                    rate = Decimal(str(description))
                    
                    # Сохраняем курс к тенге
                    CurrencyRate.objects.update_or_create(
                        from_currency=title,
                        to_currency='KZT',
                        defaults={
                            'rate': rate,
                            'source': 'nationalbank_kz',
                            'is_active': True
                        }
                    )
                    
                    # Создаем обратный курс
                    reverse_rate = Decimal('1') / rate
                    CurrencyRate.objects.update_or_create(
                        from_currency='KZT',
                        to_currency=title,
                        defaults={
                            'rate': reverse_rate,
                            'source': 'nationalbank_kz',
                            'is_active': True
                        }
                    )
                    
                    updated_count += 1
            
            # Логируем успешное обновление
            CurrencyUpdateLog.objects.create(
                source='nationalbank_kz',
                success=True,
                rates_updated=updated_count
            )
            
            self.stdout.write(f'Нацбанк КЗ: Обновлено {updated_count} курсов')
            
        except Exception as e:
            logger.error(f"Ошибка обновления Нацбанка КЗ: {str(e)}")
            CurrencyUpdateLog.objects.create(
                source='nationalbank_kz',
                success=False,
                rates_updated=0,
                error_message=str(e)
            )
            self.stdout.write(self.style.ERROR(f'Ошибка Нацбанка КЗ: {str(e)}'))
