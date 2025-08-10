from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Конфигурация приложения каталога."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    verbose_name = "Каталог"

