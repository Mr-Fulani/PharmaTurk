"""Оповещения о диске и Redis: 18–19.10.2026 диск и брокер отказали раньше HTTP-алерта."""

from collections import namedtuple
from unittest.mock import Mock, patch

import redis
from celery.schedules import crontab
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings

from apps.monitoring.resources import ResourceProblem, check_disk, check_redis, format_problems
from apps.monitoring.tasks import RESOURCES_STATE_KEY, check_server_resources

GIB = 1024**3
DiskUsage = namedtuple("DiskUsage", "total used free")


def _redis(**info):
    client = Mock()
    client.info.return_value = {"maxmemory_policy": "noeviction", "rdb_last_bgsave_status": "ok", **info}
    return client


@patch("apps.monitoring.resources.shutil.disk_usage", return_value=DiskUsage(38 * GIB, 35 * GIB, 3 * GIB))
def test_disk_below_threshold_is_reported(_usage):
    (problem,) = check_disk("/", 4)
    assert problem.key == "disk"
    assert "свободно 3,0 ГиБ из 38,0 ГиБ (порог 4 ГиБ)" in problem.text
    assert check_disk("/", 2) == []


def test_redis_memory_limit_and_failed_snapshot_are_reported():
    mib = 1024**2
    assert check_redis("Redis-брокер", "", 70, client=_redis(used_memory=60 * mib, maxmemory=192 * mib)) == []

    (memory,) = check_redis("Redis-брокер", "", 70, client=_redis(used_memory=150 * mib, maxmemory=192 * mib))
    assert memory.key == "Redis-брокер:memory" and "78 %" in memory.text

    (no_limit,) = check_redis("Redis-кэш", "", 110, client=_redis(used_memory=1800 * mib, maxmemory=0))
    assert no_limit.key == "Redis-кэш:no-limit"

    problems = check_redis(
        "Redis-брокер", "", 70, client=_redis(used_memory=mib, maxmemory=192 * mib, rdb_last_bgsave_status="err")
    )
    assert [problem.key for problem in problems] == ["Redis-брокер:bgsave"]


def test_unreachable_redis_is_reported():
    client = Mock()
    client.info.side_effect = redis.ConnectionError("refused")
    (problem,) = check_redis("Redis-брокер", "", 70, client=client)
    assert problem.key == "Redis-брокер:down"


DISK = ResourceProblem("disk", "Диск: свободно 3,0 ГиБ")
BROKER = ResourceProblem("Redis-брокер:memory", "Redis-брокер: занято 150 МиБ")


@override_settings(SERVER_RESOURCES_MONITOR_ENABLED=True, SERVER_RESOURCES_REPEAT_SECONDS=3600)
@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
@patch(
    "apps.monitoring.tasks.resources.collect_problems",
    side_effect=[[DISK], [DISK], [DISK, BROKER], [], []],
)
def test_alert_once_per_problem_then_recovery(_collect, send):
    cache.delete(RESOURCES_STATE_KEY)

    statuses = [check_server_resources()["status"] for _ in range(5)]

    assert statuses == ["alerted", "problem", "alerted", "recovered", "healthy"]
    assert send.call_count == 3
    assert "Redis-брокер" in send.call_args_list[1].args[0]
    assert "в норме" in send.call_args_list[2].args[0]


@override_settings(SERVER_RESOURCES_MONITOR_ENABLED=True)
@patch("apps.monitoring.tasks.cache.set")
@patch("apps.monitoring.tasks.cache.get", side_effect=RuntimeError("cache unavailable"))
@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
@patch("apps.monitoring.tasks.resources.collect_problems", return_value=[DISK])
def test_cache_failure_does_not_suppress_alert(_collect, send, _get, _set):
    assert check_server_resources()["status"] == "alerted"
    send.assert_called_once()


@override_settings(SERVER_RESOURCES_MONITOR_ENABLED=False)
@patch("apps.monitoring.tasks.resources.collect_problems")
def test_disabled_monitor_checks_nothing(collect):
    assert check_server_resources() == {"status": "disabled"}
    collect.assert_not_called()


def test_resources_check_runs_every_ten_minutes_on_the_default_queue():
    entry = settings.CELERY_BEAT_SCHEDULE["monitoring-server-resources"]
    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].minute == set(range(0, 60, 10))
    assert settings.CELERY_TASK_ROUTES["apps.monitoring.tasks.*"] == {"queue": "celery"}


def test_alert_text_points_to_runbook():
    text = format_problems([DISK])
    assert text.startswith("⚠️") and "Диск: свободно" in text and "PROD_DISK_AND_REDIS.md" in text
