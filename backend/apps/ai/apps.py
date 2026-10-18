from django.apps import AppConfig

class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai'
    verbose_name = 'AI Модуль'

    def ready(self):
        import apps.ai.signals  # noqa
        import apps.ai.admin_translation_memory  # noqa: F401 — отдельно от admin.py
