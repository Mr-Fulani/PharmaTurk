"""Утилиты для парсинга данных."""

import re
from decimal import Decimal
from typing import List, Optional, Union
from urllib.parse import urljoin, urlparse


def normalize_price(price_str: str) -> Optional[Decimal]:
    """Нормализует строку цены в Decimal.
    
    Args:
        price_str: Строка с ценой (например, "1,234.56 ₽" или "$99.99")
        
    Returns:
        Decimal или None при ошибке
    """
    if not price_str:
        return None
    
    # Удаляем все символы кроме цифр, точек и запятых
    cleaned = re.sub(r'[^\d.,]', '', str(price_str))
    
    if not cleaned:
        return None
    
    # Обрабатываем разные форматы
    if ',' in cleaned and '.' in cleaned:
        # Формат: 1,234.56 или 1.234,56
        parts = cleaned.replace(',', '').split('.')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Американский формат: 1,234.56
            cleaned = cleaned.replace(',', '')
        else:
            # Европейский формат: 1.234,56
            cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        # Только запятая - может быть десятичным разделителем
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Европейский формат: 123,45
            cleaned = cleaned.replace(',', '.')
        else:
            # Разделитель тысяч: 1,234
            cleaned = cleaned.replace(',', '')
    
    try:
        return Decimal(cleaned)
    except:
        return None


def clean_text(text: str) -> str:
    """Очищает текст от лишних пробелов и символов.
    
    Args:
        text: Исходный текст
        
    Returns:
        Очищенный текст
    """
    if not text:
        return ""
    
    # Удаляем лишние пробелы и переносы строк
    cleaned = re.sub(r'\s+', ' ', str(text).strip())
    
    # Удаляем управляющие символы
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
    
    return cleaned.strip()


def extract_images(base_url: str, image_elements: List[str]) -> List[str]:
    """Извлекает и нормализует URLs изображений.
    
    Args:
        base_url: Базовый URL сайта
        image_elements: Список URL изображений или относительных путей
        
    Returns:
        Список абсолютных URL изображений
    """
    images = []
    
    for img_url in image_elements:
        if not img_url:
            continue
            
        # Очищаем URL
        img_url = clean_text(img_url)
        
        # Пропускаем data: URLs и пустые
        if img_url.startswith('data:') or not img_url:
            continue
            
        # Преобразуем относительные URL в абсолютные
        if not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
            
        # Проверяем, что URL валиден
        try:
            parsed = urlparse(img_url)
            if parsed.scheme and parsed.netloc:
                images.append(img_url)
        except:
            continue
            
    return images


def extract_currency(price_str: str) -> str:
    """Извлекает валюту из строки цены.
    
    Args:
        price_str: Строка с ценой
        
    Returns:
        Код валюты (RUB, USD, EUR, TRY)
    """
    if not price_str:
        return "RUB"
    
    price_str = str(price_str).upper()
    
    # Маппинг символов валют
    currency_symbols = {
        '₽': 'RUB',
        'РУБ': 'RUB',
        'RUB': 'RUB',
        '$': 'USD', 
        'USD': 'USD',
        '€': 'EUR',
        'EUR': 'EUR',
        '₺': 'TRY',
        'TL': 'TRY',
        'TRY': 'TRY',
        'ЛИРА': 'TRY',
    }
    
    for symbol, currency in currency_symbols.items():
        if symbol in price_str:
            return currency
            
    return "RUB"  # По умолчанию рубли


def normalize_url(url: str, base_url: str) -> str:
    """Нормализует URL относительно базового.
    
    Args:
        url: URL для нормализации
        base_url: Базовый URL
        
    Returns:
        Абсолютный URL
    """
    if not url:
        return ""
        
    url = clean_text(url)
    
    if url.startswith(('http://', 'https://')):
        return url
        
    return urljoin(base_url, url)


def extract_sku_from_text(text: str) -> Optional[str]:
    """Извлекает SKU/артикул из текста.
    
    Args:
        text: Текст для поиска
        
    Returns:
        SKU или None
    """
    if not text:
        return None
        
    # Паттерны для поиска артикулов
    patterns = [
        r'(?:SKU|Артикул|Код|Code):\s*([A-Z0-9\-_]+)',
        r'(?:SKU|Артикул|Код|Code)\s*([A-Z0-9\-_]+)',
        r'\b([A-Z]{2,}\d{4,})\b',  # Общий паттерн: 2+ букв + 4+ цифр
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.upper())
        if match:
            return match.group(1)
            
    return None


def extract_barcode_from_text(text: str) -> Optional[str]:
    """Извлекает штрихкод из текста.
    
    Args:
        text: Текст для поиска
        
    Returns:
        Штрихкод или None
    """
    if not text:
        return None
        
    # Паттерны для штрихкодов
    patterns = [
        r'(?:Штрихкод|Barcode|EAN):\s*(\d{8,14})',
        r'(?:Штрихкод|Barcode|EAN)\s*(\d{8,14})',
        r'\b(\d{13})\b',  # EAN-13
        r'\b(\d{12})\b',  # UPC-A
        r'\b(\d{8})\b',   # EAN-8
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            barcode = match.group(1)
            # Проверяем длину штрихкода
            if len(barcode) in [8, 12, 13, 14]:
                return barcode
                
    return None
