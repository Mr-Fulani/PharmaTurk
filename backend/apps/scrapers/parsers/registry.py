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
            raw_url = str(url or "").strip()
            if not raw_url:
                return None
            # urlparse("massimodutti") считает строку path и оставляет
            # netloc пустым. Неизвестное имя parser_class не должно
            # превращаться в URL-fallback и случайно выбирать чужой парсер.
            parsed = urlparse(raw_url if "://" in raw_url else f"//{raw_url}")
            domain = parsed.netloc.lower()
            if not domain or ("." not in domain and domain != "localhost"):
                return None
            
            # Убираем www. если есть
            if domain.startswith('www.'):
                domain = domain[4:]
            
            parser_name = self._domain_mapping.get(domain)
            if parser_name:
                return self._parsers.get(parser_name)
            
            # Пробуем найти по части домена
            for registered_domain, parser_name in self._domain_mapping.items():
                registered_domain = registered_domain.removeprefix("www.")
                if domain == registered_domain or domain.endswith(f".{registered_domain}"):
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
    """Авто-обнаружение парсеров.

    Импортирует все модули пакета ``parsers`` и регистрирует каждый конкретный
    подкласс :class:`BaseScraper`, определённый в самом модуле. Новый парсер
    попадает в реестр автоматически — достаточно положить файл с подклассом
    ``BaseScraper`` в пакет, отдельный список вести не нужно.

    Общие (абстрактные) базовые классы не регистрируются: у них остаются
    нереализованные абстрактные методы, поэтому ``inspect.isabstract`` их
    отсеивает.
    """
    import importlib
    import inspect
    import pkgutil

    log = logging.getLogger(__name__)
    package = importlib.import_module(__package__)

    for module_info in pkgutil.iter_modules(package.__path__):
        module_name = module_info.name
        # registry — это мы сами; base — пакет с абстракцией, не парсеры.
        if module_name in ("registry", "base"):
            continue
        full_name = f"{__package__}.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:  # noqa: BLE001 — кривой модуль не должен ронять старт
            log.warning("Не удалось импортировать модуль парсера %s: %s", full_name, exc)
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseScraper)
                and obj is not BaseScraper
                and not inspect.isabstract(obj)
                # только классы, определённые в этом модуле (не импортированные)
                and obj.__module__ == module.__name__
            ):
                try:
                    _registry.register(obj)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Не удалось зарегистрировать парсер %s: %s", obj.__name__, exc)
