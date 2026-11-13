from django.db import models


class CspViolation(models.Model):
    """Отчёт браузера о нарушении CSP (TD-033), из ``/api/csp-report/``.

    Лог контейнера пропадает при каждом выпуске, поэтому отчёты хранятся в базе
    30 дней (``monitoring.prune_csp_violations``); сводка — ``manage.py csp_violations``.
    Адреса без query-строк, IP не храним.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    directive = models.CharField(max_length=80, blank=True)
    blocked = models.CharField(max_length=300, blank=True)
    page = models.CharField(max_length=300, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.directive} {self.blocked} on {self.page}"
