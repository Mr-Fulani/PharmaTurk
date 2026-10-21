"""Ресурсы сервера: свободное место на диске и память обоих Redis.

Watchdog проверяет только HTTP. 18 и 19.10.2026 диск заполнился, брокер Redis
отказал в записи (MISCONF), и сайт отдавал 503 раньше, чем это стало видно по
HTTP. Проверка идёт из воркера Celery: его корень — overlay на диске хоста,
поэтому ``shutil.disk_usage("/")`` — свободное место хоста (как
``db_backup.restore_check``). Бэкапы перед деплоем (~/backups, по ≈ 690 МБ)
воркер не читает — они закрыты правами 700; их рост виден по свободному месту,
а старые копии удаляет ``deploy.sh`` (см. docs/PROD_DISK_AND_REDIS.md).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

import redis
from django.conf import settings

GIB = 1024**3
MIB = 1024**2


@dataclass(frozen=True)
class ResourceProblem:
    key: str  # стабильный ключ: по нему алерт не повторяется каждые 10 минут
    text: str


def _gib(value: float) -> str:
    return f"{value / GIB:.1f}".replace(".", ",") + " ГиБ"


def _mib(value: float) -> str:
    return f"{value / MIB:.0f} МиБ"


def check_disk(path: str, min_free_gib: float) -> list[ResourceProblem]:
    usage = shutil.disk_usage(path)
    if usage.free >= min_free_gib * GIB:
        return []
    return [
        ResourceProblem(
            "disk",
            f"Диск: свободно {_gib(usage.free)} из {_gib(usage.total)} (порог {min_free_gib:g} ГиБ). "
            "При нуле Redis запрещает запись, и сайт отдаёт 503.",
        )
    ]


def check_redis(name: str, url: str, max_percent: float, *, client=None) -> list[ResourceProblem]:
    """used_memory к maxmemory и последний снимок на диск (его сбой — MISCONF, запрет записи)."""
    try:
        info = (client or redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)).info()
    except redis.RedisError as exc:
        return [ResourceProblem(f"{name}:down", f"{name}: недоступен ({type(exc).__name__}).")]
    problems = []
    used, limit = int(info.get("used_memory") or 0), int(info.get("maxmemory") or 0)
    if not limit:
        problems.append(
            ResourceProblem(f"{name}:no-limit", f"{name}: maxmemory не задан, занято {_mib(used)} — растёт без предела.")
        )
    elif used * 100 >= limit * max_percent:
        problems.append(
            ResourceProblem(
                f"{name}:memory",
                f"{name}: занято {_mib(used)} из {_mib(limit)} ({used * 100 // limit} %, порог {max_percent:g} %, "
                f"политика {info.get('maxmemory_policy', '?')}).",
            )
        )
    if info.get("rdb_last_bgsave_status", "ok") != "ok":
        problems.append(
            ResourceProblem(
                f"{name}:bgsave",
                f"{name}: последний снимок на диск не удался — Redis может запретить запись (MISCONF).",
            )
        )
    return problems


def collect_problems() -> list[ResourceProblem]:
    # Кэш с allkeys-lru держится у maxmemory — это норма; его порог выше 100 %,
    # он срабатывает, только если вытеснение не работает.
    return [
        *check_disk("/", settings.SERVER_DISK_MIN_FREE_GB),
        *check_redis("Redis-брокер", settings.CELERY_BROKER_URL, settings.REDIS_BROKER_MAX_MEMORY_PERCENT),
        *check_redis("Redis-кэш", settings.REDIS_CACHE_URL, settings.REDIS_CACHE_MAX_MEMORY_PERCENT),
    ]


def format_problems(problems: list[ResourceProblem]) -> str:
    return "\n".join(
        ["⚠️ Mudaroba: ресурсы сервера на пределе", ""]
        + [f"• {problem.text}" for problem in problems]
        + ["", "Что делать: docs/PROD_DISK_AND_REDIS.md"]
    )
