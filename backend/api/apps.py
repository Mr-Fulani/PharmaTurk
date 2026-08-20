from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Register drf-spectacular extensions after Django has loaded apps.
        from . import schema  # noqa: F401
