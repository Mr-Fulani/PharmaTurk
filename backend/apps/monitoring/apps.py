from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoring"

    def ready(self) -> None:
        from . import checks  # noqa: F401
