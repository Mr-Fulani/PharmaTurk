from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Конфигурация приложения платежей."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    verbose_name = "Платежи"

