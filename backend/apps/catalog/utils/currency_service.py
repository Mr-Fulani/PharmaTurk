import requests
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Dict, Optional, Tuple
from django.conf import settings
from django.core.cache import cache
from ..currency_models import CurrencyRate, CurrencyUpdateLog, GlobalCurrencySettings

logger = logging.getLogger(__name__)

# Символы → коды валют (для lookup курсов)
_CURRENCY_SYMBOL_MAP = {
    "₽": "RUB",
    "руб": "RUB",
    "руб.": "RUB",
    "₺": "TRY",
    "tl": "TRY",
    "$": "USD",
    "€": "EUR",
    "₸": "KZT",
    "тг": "KZT",
    "тнг": "KZT",
}


def _normalize_currency_for_rate(currency: str) -> str:
    """Нормализует валюту для поиска курса: ₽→RUB, руб→RUB и т.п."""
    if not currency:
        return currency
    s = str(currency).strip()
    for symbol, code in _CURRENCY_SYMBOL_MAP.items():
        if symbol.lower() in s.lower() or s == symbol:
            return code
    return s.upper() if len(s) == 3 else s


class CurrencyRateService:
    """Сервис для получения и обновления курсов валют"""
    
    CACHE_TIMEOUT = 3600 * 4  # 4 часа
    
    API_ENDPOINTS = {
        'centralbank_rf': 'https://www.cbr-xml-daily.ru/daily_json.js',
        'nationalbank_kz': 'https://nationalbank.kz/rss/rates_all.xml',
        'centralbank_tr': 'https://www.tcmb.gov.tr/kurlar/today.xml',
        'openexchangerates': 'https://openexchangerates.org/api/latest.json',
    }
    
    BASE_CURRENCIES = {
        'centralbank_rf': 'RUB',
        'nationalbank_kz': 'KZT', 
        'centralbank_tr': 'TRY',
        'openexchangerates': 'USD',
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
    
    def get_rates_from_source(self, source: str) -> Dict[str, Decimal]:
        if source not in self.API_ENDPOINTS:
            raise ValueError(f"Unknown source: {source}")
        try:
            response = self.session.get(self.API_ENDPOINTS[source])
            response.raise_for_status()
            if source == 'centralbank_rf':
                return self._parse_cbr_response(response.json())
            elif source == 'openexchangerates':
                return self._parse_openexchangerates_response(response.json())
            elif source == 'nationalbank_kz':
                return self._parse_nbk_response(response.text)
            elif source == 'centralbank_tr':
                return self._parse_tcmb_response(response.text)
        except Exception as e:
            logger.error(f"Error fetching rates from {source}: {str(e)}")
            raise
    
    def _parse_cbr_response(self, data: Dict) -> Dict[str, Decimal]:
        rates = {}
        base_currency = 'RUB'
        for currency_data in data['Valute'].values():
            code = currency_data['CharCode']
            if code in ['USD', 'EUR', 'TRY', 'KZT']:
                value = Decimal(str(currency_data['Value'])) / Decimal(str(currency_data['Nominal']))
                rates[f"{code}-{base_currency}"] = value
                rates[f"{base_currency}-{code}"] = Decimal('1') / value
        # USDT и кросс-курсы USD-* (как в services/currency_service — тот же источник правды)
        usd_to_rub = rates.get(f"USD-{base_currency}")
        if usd_to_rub:
            markup = GlobalCurrencySettings.load().usdt_markup_percentage
            usdt_modifier = Decimal('1') + (markup / Decimal('100'))
            usdt_to_rub = usd_to_rub / usdt_modifier
            rates[f"USDT-{base_currency}"] = usdt_to_rub
            rates[f"{base_currency}-USDT"] = Decimal('1') / usdt_to_rub
            for currency in ['EUR', 'TRY', 'KZT']:
                curr_to_rub = rates.get(f"{currency}-{base_currency}")
                if curr_to_rub:
                    usdt_to_curr = usdt_to_rub / curr_to_rub
                    rates[f"USDT-{currency}"] = usdt_to_curr
                    rates[f"{currency}-USDT"] = Decimal('1') / usdt_to_curr
                    usd_to_curr = usd_to_rub / curr_to_rub
                    rates[f"USD-{currency}"] = usd_to_curr
                    rates[f"{currency}-USD"] = Decimal('1') / usd_to_curr
        return rates
    
    def _parse_openexchangerates_response(self, data: Dict) -> Dict[str, Decimal]:
        rates = {}
        base_currency = data.get('base', 'USD')
        for currency, rate in data['rates'].items():
            if currency in ['RUB', 'EUR', 'TRY', 'KZT']:
                rate_decimal = Decimal(str(rate))
                rates[f"{base_currency}-{currency}"] = rate_decimal
                rates[f"{currency}-{base_currency}"] = Decimal('1') / rate_decimal
        markup = GlobalCurrencySettings.load().usdt_markup_percentage
        usdt_modifier = Decimal('1') + (markup / Decimal('100'))
        rates[f"USDT-{base_currency}"] = Decimal('1') / usdt_modifier
        rates[f"{base_currency}-USDT"] = usdt_modifier
        for currency in ['RUB', 'EUR', 'TRY', 'KZT']:
            usd_to_curr = rates.get(f"{base_currency}-{currency}")
            if usd_to_curr:
                usdt_to_curr = usd_to_curr / usdt_modifier
                rates[f"USDT-{currency}"] = usdt_to_curr
                rates[f"{currency}-USDT"] = Decimal('1') / usdt_to_curr
        return rates
    
    def _parse_nbk_response(self, xml_data: str) -> Dict[str, Decimal]:
        from xml.etree import ElementTree as ET
        try:
            root = ET.fromstring(xml_data)
            rates = {}
            base_currency = 'KZT'
            for item in root.findall('.//item'):
                title = item.find('title').text
                description = item.find('description').text
                if title in ['USD', 'EUR', 'RUB', 'TRY']:
                    rate = Decimal(str(description))
                    rates[f"{title}-{base_currency}"] = rate
                    rates[f"{base_currency}-{title}"] = Decimal('1') / rate
            usd_to_kzt = rates.get(f"USD-{base_currency}")
            if usd_to_kzt:
                markup = GlobalCurrencySettings.load().usdt_markup_percentage
                usdt_modifier = Decimal('1') + (markup / Decimal('100'))
                usdt_to_kzt = usd_to_kzt / usdt_modifier
                rates[f"USDT-{base_currency}"] = usdt_to_kzt
                rates[f"{base_currency}-USDT"] = Decimal('1') / usdt_to_kzt
                for currency in ['EUR', 'RUB', 'TRY']:
                    curr_to_kzt = rates.get(f"{currency}-{base_currency}")
                    if curr_to_kzt:
                        usdt_to_curr = usdt_to_kzt / curr_to_kzt
                        rates[f"USDT-{currency}"] = usdt_to_curr
                        rates[f"{currency}-USDT"] = Decimal('1') / usdt_to_curr
            return rates
        except Exception as e:
            logger.error(f"Error parsing NBK XML: {str(e)}")
            raise
    
    def _parse_tcmb_response(self, xml_data: str) -> Dict[str, Decimal]:
        from xml.etree import ElementTree as ET
        try:
            root = ET.fromstring(xml_data)
            rates = {}
            base_currency = 'TRY'
            for currency in root.findall('.//Currency'):
                code = currency.get('CurrencyCode')
                if code in ['USD', 'EUR', 'RUB', 'KZT']:
                    forexbuying = currency.find('ForexBuying')
                    if forexbuying is not None and forexbuying.text:
                        rate = Decimal(str(forexbuying.text.replace(',', '.')))
                        rates[f"{code}-{base_currency}"] = rate
                        rates[f"{base_currency}-{code}"] = Decimal('1') / rate
            usd_to_try = rates.get(f"USD-{base_currency}")
            if usd_to_try:
                markup = GlobalCurrencySettings.load().usdt_markup_percentage
                usdt_modifier = Decimal('1') + (markup / Decimal('100'))
                usdt_to_try = usd_to_try / usdt_modifier
                rates[f"USDT-{base_currency}"] = usdt_to_try
                rates[f"{base_currency}-USDT"] = Decimal('1') / usdt_to_try
                for currency in ['EUR', 'RUB', 'KZT']:
                    curr_to_try = rates.get(f"{currency}-{base_currency}")
                    if curr_to_try:
                        usdt_to_curr = usdt_to_try / curr_to_try
                        rates[f"USDT-{currency}"] = usdt_to_curr
                        rates[f"{currency}-USDT"] = Decimal('1') / usdt_to_curr
            return rates
        except Exception as e:
            logger.error(f"Error parsing TCMB XML: {str(e)}")
            raise
    
    def update_rates(self, source: str = None) -> Tuple[bool, str]:
        start_time = datetime.now()
        if source is None:
            sources = ['centralbank_rf', 'openexchangerates']
        else:
            sources = [source]
        total_updated = 0
        last_error = None
        for src in sources:
            try:
                rates = self.get_rates_from_source(src)
                for pair, rate in rates.items():
                    from_currency, to_currency = pair.split('-')
                    currency_rate, created = CurrencyRate.objects.update_or_create(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        defaults={
                            'rate': rate,
                            'source': src,
                            'is_active': True
                        }
                    )
                    if not created:
                        currency_rate.rate = rate
                        currency_rate.source = src
                        currency_rate.save()
                    total_updated += 1
                try:
                    cache.set(f'currency_rates_{src}', rates, self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Cache set failed for currency_rates_{src}: {e}")
                execution_time = (datetime.now() - start_time).total_seconds()
                CurrencyUpdateLog.objects.create(
                    source=src,
                    success=True,
                    rates_updated=total_updated,
                    execution_time_seconds=execution_time
                )
                logger.info(f"Successfully updated {total_updated} rates from {src}")
                return True, f"Updated {total_updated} rates from {src}"
            except Exception as e:
                last_error = str(e)
                logger.error(f"Failed to update rates from {src}: {last_error}")
                execution_time = (datetime.now() - start_time).total_seconds()
                CurrencyUpdateLog.objects.create(
                    source=src,
                    success=False,
                    rates_updated=0,
                    error_message=last_error,
                    execution_time_seconds=execution_time
                )
        return False, f"All sources failed. Last error: {last_error}"
    
    def _derive_usdt_rate_via_usd(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """
        USDT нет на биржевых API; в БД пары USDT могли не появиться после старых обновлений.
        Считаем курс через USD и GlobalCurrencySettings.usdt_markup_percentage (как при парсинге).
        """
        markup = GlobalCurrencySettings.load().usdt_markup_percentage
        usdt_modifier = Decimal('1') + (markup / Decimal('100'))
        if from_currency == 'USD' and to_currency == 'USDT':
            return usdt_modifier
        if from_currency == 'USDT' and to_currency == 'USD':
            return Decimal('1') / usdt_modifier
        if to_currency == 'USDT':
            x_to_usd = self.get_rate(from_currency, 'USD', allow_usdt_derivation=False)
            if x_to_usd is not None:
                return (x_to_usd * usdt_modifier).quantize(Decimal('0.0000001'))
        if from_currency == 'USDT':
            usd_to_x = self.get_rate('USD', to_currency, allow_usdt_derivation=False)
            if usd_to_x is not None:
                return (usd_to_x / usdt_modifier).quantize(Decimal('0.0000001'))
        return None

    def get_rate(
        self, from_currency: str, to_currency: str, *, allow_usdt_derivation: bool = True
    ) -> Optional[Decimal]:
        from_currency = _normalize_currency_for_rate(from_currency or "")
        to_currency = _normalize_currency_for_rate(to_currency or "")
        if not from_currency or not to_currency:
            return None
        if from_currency == to_currency:
            return Decimal('1')
        cache_key = f'rate_{from_currency}_{to_currency}'
        try:
            cached_rate = cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Cache get failed for {cache_key}: {e}")
            cached_rate = None
        if cached_rate:
            return cached_rate
        try:
            rate_obj = CurrencyRate.objects.get(
                from_currency=from_currency,
                to_currency=to_currency,
                is_active=True
            )
            try:
                cache.set(cache_key, rate_obj.rate, 300)
            except Exception as e:
                logger.warning(f"Cache set failed for {cache_key}: {e}")
            return rate_obj.rate
        except CurrencyRate.DoesNotExist:
            pass

        def _get_direct_rate(src: str, dst: str) -> Optional[Decimal]:
            try:
                direct = CurrencyRate.objects.get(
                    from_currency=src,
                    to_currency=dst,
                    is_active=True
                )
                return direct.rate
            except CurrencyRate.DoesNotExist:
                try:
                    reverse = CurrencyRate.objects.get(
                        from_currency=dst,
                        to_currency=src,
                        is_active=True
                    )
                    if reverse.rate == 0:
                        return None
                    return Decimal('1') / reverse.rate
                except CurrencyRate.DoesNotExist:
                    return None

        pivots = ['RUB', 'USD', 'EUR', 'TRY', 'KZT']
        for pivot in pivots:
            if pivot == from_currency or pivot == to_currency:
                continue
            first = _get_direct_rate(from_currency, pivot)
            if first is None:
                continue
            second = _get_direct_rate(pivot, to_currency)
            if second is None:
                continue
            derived = (first * second).quantize(Decimal('0.0000001'))
            try:
                cache.set(cache_key, derived, 300)
            except Exception as e:
                logger.warning(f"Cache set failed for {cache_key}: {e}")
            return derived

        if allow_usdt_derivation and (from_currency == 'USDT' or to_currency == 'USDT'):
            synthetic = self._derive_usdt_rate_via_usd(from_currency, to_currency)
            if synthetic is not None:
                try:
                    cache.set(cache_key, synthetic, 300)
                except Exception as e:
                    logger.warning(f"Cache set failed for {cache_key}: {e}")
                return synthetic

        logger.warning(f"Rate not found: {from_currency} → {to_currency}")
        return None
    
    def get_all_rates(self) -> Dict[str, Dict[str, Decimal]]:
        rates = {}
        for rate in CurrencyRate.objects.filter(is_active=True):
            pair = f"{rate.from_currency}-{rate.to_currency}"
            rates[pair] = rate.rate
        return rates
