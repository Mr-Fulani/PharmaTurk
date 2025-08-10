from django.apps import AppConfig


class VapiConfig(AppConfig):
    """Конфигурация приложения интеграции с Vapi."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vapi"
    verbose_name = "Vapi интеграция"

