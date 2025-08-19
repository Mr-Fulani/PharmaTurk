"""Конфигурация Django-приложения для парсеров."""

from django.apps import AppConfig


class ScrapersConfig(AppConfig):
    """Конфигурация приложения scrapers."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scrapers'
    verbose_name = 'Парсеры сайтов'
    
    def ready(self):
        """Инициализация приложения при запуске Django."""
        # Регистрируем парсеры в реестре
        from .parsers.registry import register_default_parsers
        register_default_parsers()
