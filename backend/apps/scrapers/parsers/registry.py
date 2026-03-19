"""Реестр парсеров для различных сайтов."""

import logging
from typing import Dict, List, Optional, Type
from urllib.parse import urlparse

from ..base.scraper import BaseScraper


class ParserRegistry:
    """Реестр всех доступных парсеров."""
    
    def __init__(self):
        self._parsers: Dict[str, Type[BaseScraper]] = {}
        self._domain_mapping: Dict[str, str] = {}
        self.logger = logging.getLogger(__name__)
    
    def register(self, parser_class: Type[BaseScraper]):
        """Регистрирует парсер в реестре.
        
        Args:
            parser_class: Класс парсера
        """
        # Создаем временный экземпляр для получения метаданных
        temp_instance = parser_class("http://example.com")
        
        name = temp_instance.get_name()
        domains = temp_instance.get_supported_domains()
        
        # Регистрируем парсер
        self._parsers[name] = parser_class
        
        # Регистрируем домены
        for domain in domains:
            self._domain_mapping[domain.lower()] = name
        
        self.logger.info(f"Зарегистрирован парсер '{name}' для доменов: {domains}")
    
    def get_parser_by_name(self, name: str) -> Optional[Type[BaseScraper]]:
        """Получает класс парсера по имени.
        
        Args:
            name: Имя парсера
            
        Returns:
            Класс парсера или None
        """
        return self._parsers.get(name)
    
    def get_parser_by_url(self, url: str) -> Optional[Type[BaseScraper]]:
        """Получает класс парсера по URL.
        
        Args:
            url: URL сайта
            
        Returns:
            Класс парсера или None
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Убираем www. если есть
            if domain.startswith('www.'):
                domain = domain[4:]
            
            parser_name = self._domain_mapping.get(domain)
            if parser_name:
                return self._parsers.get(parser_name)
            
            # Пробуем найти по части домена
            for registered_domain, parser_name in self._domain_mapping.items():
                if domain.endswith(registered_domain) or registered_domain.endswith(domain):
                    return self._parsers.get(parser_name)
            
        except Exception as e:
            self.logger.error(f"Ошибка при определении парсера для URL {url}: {e}")
        
        return None
    
    def get_all_parsers(self) -> Dict[str, Type[BaseScraper]]:
        """Возвращает все зарегистрированные парсеры.
        
        Returns:
            Словарь {имя: класс_парсера}
        """
        return self._parsers.copy()
    
    def get_supported_domains(self) -> List[str]:
        """Возвращает список всех поддерживаемых доменов.
        
        Returns:
            Список доменов
        """
        return list(self._domain_mapping.keys())
    
    def is_supported(self, url: str) -> bool:
        """Проверяет, поддерживается ли URL.
        
        Args:
            url: URL для проверки
            
        Returns:
            True если URL поддерживается
        """
        return self.get_parser_by_url(url) is not None


# Глобальный экземпляр реестра
_registry = ParserRegistry()


def register_parser(parser_class: Type[BaseScraper]):
    """Декоратор для регистрации парсера.
    
    Args:
        parser_class: Класс парсера
        
    Returns:
        Класс парсера
    """
    _registry.register(parser_class)
    return parser_class


def get_parser(url_or_name: str) -> Optional[Type[BaseScraper]]:
    """Получает парсер по URL или имени.
    
    Args:
        url_or_name: URL сайта или имя парсера
        
    Returns:
        Класс парсера или None
    """
    # Сначала пробуем как имя
    parser = _registry.get_parser_by_name(url_or_name)
    if parser:
        return parser
    
    # Затем как URL
    return _registry.get_parser_by_url(url_or_name)


def get_all_parsers() -> Dict[str, Type[BaseScraper]]:
    """Возвращает все зарегистрированные парсеры."""
    return _registry.get_all_parsers()


def get_supported_domains() -> List[str]:
    """Возвращает список поддерживаемых доменов."""
    return _registry.get_supported_domains()


def is_url_supported(url: str) -> bool:
    """Проверяет, поддерживается ли URL."""
    return _registry.is_supported(url)


def register_default_parsers():
    """Регистрирует парсеры по умолчанию."""
    try:
        # Импортируем и регистрируем парсеры
        from .ilacabak import IlacabakParser
        from .zara import ZaraParser
        from .instagram import InstagramParser
        from .ummaland import UmmalandParser
        
        _registry.register(IlacabakParser)
        _registry.register(ZaraParser)
        _registry.register(InstagramParser)
        _registry.register(UmmalandParser)
        
    except ImportError as e:
        logging.getLogger(__name__).warning(f"Не удалось импортировать некоторые парсеры: {e}")
