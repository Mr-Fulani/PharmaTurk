"""Django application configuration owned by the project."""

from django.contrib.admin.apps import AdminConfig


class MudarobaAdminConfig(AdminConfig):
    """Use the project AdminSite while preserving Django admin autodiscovery."""

    default_site = "config.admin.MudarobaAdminSite"
