"""Сводка отчётов CSP из базы (TD-033): что браузеры заблокировали и где.

    manage.py csp_violations              # за 24 часа
    manage.py csp_violations --hours 72

Строки группируются по директиве, источнику (путь заявки /wsync/<номер> обрезан), странице
(у товаров и разделов — только раздел сайта) и устройству по User-Agent.
"""

import re
from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.monitoring.models import CspViolation

_SECTION_RE = re.compile(r"^(https?://[^/]+)?(/en)?/(product|products|categories|brand|drugs|blog|search|catalog)/.*")
_DEVICES = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Macintosh", "Mac"))


def _device(user_agent: str) -> str:
    return next((name for marker, name in _DEVICES if marker in user_agent), "другое")


def _blocked(value: str) -> str:
    return re.sub(r"^https://[a-z0-9]+\.ru/wsync/\d+$", "<случайный домен>.ru/wsync (Метрика)", value)


class Command(BaseCommand):
    help = "Сводка нарушений CSP из базы за последние часы."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(hours=options["hours"])
        rows = CspViolation.objects.filter(created_at__gte=since)
        counts = Counter()
        for directive, blocked, page, user_agent in rows.values_list("directive", "blocked", "page", "user_agent"):
            page = _SECTION_RE.sub(lambda m: f"{m.group(2) or ''}/{m.group(3)}/…", page)
            counts[(directive, _blocked(blocked), page, _device(user_agent))] += 1
        self.stdout.write(f"Отчётов CSP за {options['hours']} ч: {sum(counts.values())}")
        for (directive, blocked, page, device), count in counts.most_common(50):
            self.stdout.write(f"{count:5}  {directive} blocked {blocked} on {page} [{device}]")
