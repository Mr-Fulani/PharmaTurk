"""Инициализация Celery для проекта.

Celery используется для фоновых задач (парсинг, обновление цен/остатков, уведомления).
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("pharmaturk")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Автоматическое обнаружение задач во всех приложениях Django
app.autodiscover_tasks()

# Явно импортируем задачи из приложения orders для гарантированной регистрации
try:
    from apps.orders import tasks  # noqa: F401
except ImportError:
    pass

