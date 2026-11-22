"""Django application configuration owned by the project."""

from django.contrib.admin.apps import AdminConfig


class MudarobaAdminConfig(AdminConfig):
    """Use the project AdminSite while preserving Django admin autodiscovery."""

    default_site = "config.admin.MudarobaAdminSite"

    def ready(self):
        super().ready()
        # У django-otp нет русского перевода: названия разделов второго фактора
        # в админке задаём здесь (docs/ADMIN_TWO_FACTOR.md).
        from django.apps import apps
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice._meta.verbose_name = "приложение для кодов (второй фактор)"
        TOTPDevice._meta.verbose_name_plural = "Второй фактор: приложения сотрудников"
        StaticDevice._meta.verbose_name = "набор запасных кодов (второй фактор)"
        StaticDevice._meta.verbose_name_plural = "Второй фактор: запасные коды сотрудников"
        apps.get_app_config("otp_totp").verbose_name = "Второй фактор: приложения"
        apps.get_app_config("otp_static").verbose_name = "Второй фактор: запасные коды"
