"""Конфигурация приложения settings."""

from django.apps import AppConfig


class SettingsConfig(AppConfig):
    """Конфигурация приложения настроек сайта."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.settings'
    verbose_name = 'Настройки сайта'
    
    def ready(self):
        """Инициализация приложения при запуске Django."""
        # Импортируем admin для регистрации моделей
        import apps.settings.admin  # noqa

