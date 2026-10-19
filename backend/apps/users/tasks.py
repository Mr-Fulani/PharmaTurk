"""Celery-задачи пользователей и сессий."""
from celery import shared_task
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.utils import timezone


@shared_task(name="users.clear_expired_sessions")
def clear_expired_sessions() -> dict:
    """Удалить просроченные сессии Django (``manage.py clearsessions``).

    Без расписания таблица ``django_session`` только растёт: анонимная корзина и
    избранное открывают сессию на каждого посетителя без cookie, включая ботов.
    У ``Session`` нет связей и сигналов, поэтому это один ``DELETE`` без загрузки
    строк в память.
    """
    expired = Session.objects.filter(expire_date__lt=timezone.now()).count()
    call_command("clearsessions")
    return {"deleted_sessions": expired}
