from django.apps import AppConfig


class DrugCheckConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drug_check"
    verbose_name = "Проверка лекарств"
