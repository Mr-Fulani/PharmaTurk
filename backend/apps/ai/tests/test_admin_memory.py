from django.contrib.admin.sites import AdminSite
from django.contrib.admin.widgets import ForeignKeyRawIdWidget
from django.test import RequestFactory

from apps.ai.admin import AIProcessingLogAdmin
from apps.ai.models import AIProcessingLog


def test_ai_processing_log_admin_avoids_large_foreign_key_selects():
    model_admin = AIProcessingLogAdmin(AIProcessingLog, AdminSite())
    request = RequestFactory().get('/admin/ai/aiprocessinglog/1/change/')

    form_class = model_admin.get_form(request)

    for field_name in ('product', 'suggested_category', 'processed_by'):
        assert isinstance(
            form_class.base_fields[field_name].widget,
            ForeignKeyRawIdWidget,
        )
