from datetime import timedelta

import pytest
from celery.schedules import crontab
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.users.tasks import clear_expired_sessions


def _session(expire_in):
    store = SessionStore()
    store["cart_session_key"] = "x"
    store.create()
    Session.objects.filter(session_key=store.session_key).update(
        expire_date=timezone.now() + expire_in
    )
    return store.session_key


@pytest.mark.django_db
def test_deletes_only_expired_sessions():
    expired = [_session(timedelta(days=-1)), _session(timedelta(days=-90))]
    alive = _session(timedelta(days=3))

    result = clear_expired_sessions.run()

    assert result == {"deleted_sessions": 2}
    assert list(Session.objects.values_list("session_key", flat=True)) == [alive]
    assert not Session.objects.filter(session_key__in=expired).exists()


def test_runs_nightly_in_quiet_hour():
    entry = settings.CELERY_BEAT_SCHEDULE["users-clear-expired-sessions"]

    assert entry["task"] == "users.clear_expired_sessions"
    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].hour == {4}
    assert entry["schedule"].minute == {0}
