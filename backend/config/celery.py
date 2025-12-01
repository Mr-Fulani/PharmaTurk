"""Инициализация Celery для проекта.

Celery используется для фоновых задач (парсинг, обновление цен/остатков, уведомления).
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("pharmaturk")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

