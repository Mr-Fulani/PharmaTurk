"""Инициализация пакета конфигурации проекта."""

try:
    from .celery import app as celery_app
    __all__ = ("celery_app",)
except ImportError:
    # Celery не установлен, пропускаем импорт
    celery_app = None
    __all__ = ()

