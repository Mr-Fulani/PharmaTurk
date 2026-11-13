"""Отчёты CSP в базе (TD-033): сводка и очистка старых."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.monitoring.models import CspViolation
from apps.monitoring.tasks import prune_csp_violations

pytestmark = pytest.mark.django_db

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15"


def test_summary_groups_by_section_and_device_and_hides_wsync_number():
    for number in ("111", "222"):
        CspViolation.objects.create(
            directive="script-src-elem", blocked=f"https://ymz0eeqo0k.ru/wsync/{number}",
            page=f"https://mudaroba.com/product/oroferon-{number}", user_agent=IPHONE,
        )
    CspViolation.objects.create(directive="img-src", blocked="https://x.example/a.png", page="https://mudaroba.com/")
    old = CspViolation.objects.create(directive="img-src", blocked="https://old.example/", page="/")
    CspViolation.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=30))

    out = StringIO()
    call_command("csp_violations", stdout=out)
    text = out.getvalue()

    assert "Отчётов CSP за 24 ч: 3" in text
    assert "    2  script-src-elem blocked <случайный домен>.ru/wsync (Метрика) on /product/… [iPhone]" in text
    assert "old.example" not in text


def test_prune_keeps_last_30_days():
    fresh = CspViolation.objects.create(directive="img-src")
    stale = CspViolation.objects.create(directive="img-src")
    CspViolation.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(days=31))

    assert prune_csp_violations() == {"deleted_csp_violations": 1}
    assert list(CspViolation.objects.values_list("pk", flat=True)) == [fresh.pk]
