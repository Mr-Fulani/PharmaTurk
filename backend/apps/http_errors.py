"""Общие ошибки при обращении к внешним HTTP-источникам."""

from urllib.parse import urlparse


class ExternalAccessBlockedError(RuntimeError):
    """Внешний источник явно отклонил авторизацию или доступ."""

    def __init__(
        self,
        message: str = "",
        *,
        source: str = "",
        status_code: int = 0,
        url: str = "",
    ):
        self.source = source
        self.status_code = status_code
        self.url = url
        if message:
            super().__init__(message)
            return
        host = urlparse(url).netloc or url
        reason = "отклонил авторизацию" if status_code == 401 else "запретил доступ"
        super().__init__(f"{source} {reason} (HTTP {status_code}, {host})")


def raise_for_blocked_status(*, status_code: int, url: str, source: str) -> None:
    """Преобразует только 401/403 в единую ошибку доступа."""
    if status_code in (401, 403):
        raise ExternalAccessBlockedError(
            source=source,
            status_code=status_code,
            url=url,
        )
