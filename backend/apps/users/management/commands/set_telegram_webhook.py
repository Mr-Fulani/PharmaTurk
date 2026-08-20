"""
Регистрирует webhook для Telegram-бота.
Telegram будет отправлять обновления (сообщения /start TOKEN) на этот URL.

Использование:
    python manage.py set_telegram_webhook

Требует в .env:
    TELEGRAM_BOT_TOKEN — токен бота
    TELEGRAM_WEBHOOK_SECRET — секрет заголовка Telegram webhook
    SITE_URL — базовый URL сайта (например https://mudaroba.com)
"""

import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Регистрирует webhook для Telegram-бота "
        "(привязка аккаунтов, уведомления)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            help="Полный URL webhook (по умолчанию: {SITE_URL}/api/users/telegram/webhook/)",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Удалить webhook",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN не задан в .env")

        site_url = getattr(settings, "SITE_URL", "") or ""
        if not options["delete"] and not options.get("url") and not site_url:
            raise CommandError(
                "SITE_URL не задан в .env. Укажите --url или задайте SITE_URL."
            )

        if options["delete"]:
            self._delete_webhook(token)
            return

        webhook_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
        if not webhook_secret:
            raise CommandError(
                "TELEGRAM_WEBHOOK_SECRET не задан: webhook без secret_token не регистрируется"
            )
        if len(webhook_secret) > 256 or not re.fullmatch(
            r"[A-Za-z0-9_-]+", webhook_secret
        ):
            raise CommandError(
                "TELEGRAM_WEBHOOK_SECRET должен содержать "
                "1–256 символов A-Z, a-z, 0-9, _ или -"
            )

        webhook_url = (
            options.get("url")
            or f"{site_url.rstrip('/')}/api/users/telegram/webhook/"
        )
        self._set_webhook(token, webhook_url, webhook_secret)

    def _set_webhook(self, token: str, url: str, webhook_secret: str) -> None:
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        try:
            resp = requests.post(
                api_url,
                json={"url": url, "secret_token": webhook_secret},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                self.stdout.write(
                    self.style.SUCCESS(f"Webhook зарегистрирован: {url}")
                )
            else:
                raise CommandError(
                    f"Ошибка Telegram API: {data.get('description', 'Неизвестно')}"
                )
        except requests.RequestException:
            # The Telegram API URL contains the bot token; do not include the
            # requests exception/URL in command output, chaining or logs.
            raise CommandError("Ошибка запроса к Telegram API") from None

    def _delete_webhook(self, token: str) -> None:
        api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        try:
            resp = requests.post(api_url, timeout=10)
            data = resp.json()
            if data.get("ok"):
                self.stdout.write(self.style.SUCCESS("Webhook удалён"))
            else:
                raise CommandError(f"Ошибка: {data.get('description', 'Неизвестно')}")
        except requests.RequestException:
            raise CommandError("Ошибка запроса к Telegram API") from None
