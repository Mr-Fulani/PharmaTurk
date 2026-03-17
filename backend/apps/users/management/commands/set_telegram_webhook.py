"""
Регистрирует webhook для Telegram-бота.
Telegram будет отправлять обновления (сообщения /start TOKEN) на этот URL.

Использование:
    python manage.py set_telegram_webhook

Требует в .env:
    TELEGRAM_BOT_TOKEN — токен бота
    SITE_URL — базовый URL сайта (например https://it-dev.space)
"""

import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Регистрирует webhook для Telegram-бота (привязка аккаунтов, уведомления)"

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
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN не задан в .env"))
            return

        site_url = getattr(settings, "SITE_URL", "") or ""
        if not options["delete"] and not options.get("url") and not site_url:
            self.stderr.write(
                self.style.ERROR(
                    "SITE_URL не задан в .env. Укажите --url или задайте SITE_URL."
                )
            )
            return

        if options["delete"]:
            self._delete_webhook(token)
            return

        webhook_url = options.get("url") or f"{site_url.rstrip('/')}/api/users/telegram/webhook/"
        self._set_webhook(token, webhook_url)

    def _set_webhook(self, token: str, url: str) -> None:
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        try:
            resp = requests.post(api_url, json={"url": url}, timeout=10)
            data = resp.json()
            if data.get("ok"):
                self.stdout.write(
                    self.style.SUCCESS(f"Webhook зарегистрирован: {url}")
                )
            else:
                self.stderr.write(
                    self.style.ERROR(f"Ошибка Telegram API: {data.get('description', 'Неизвестно')}")
                )
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Ошибка запроса: {e}"))

    def _delete_webhook(self, token: str) -> None:
        api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        try:
            resp = requests.post(api_url, timeout=10)
            data = resp.json()
            if data.get("ok"):
                self.stdout.write(self.style.SUCCESS("Webhook удалён"))
            else:
                self.stderr.write(
                    self.style.ERROR(f"Ошибка: {data.get('description', 'Неизвестно')}")
                )
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Ошибка запроса: {e}"))
