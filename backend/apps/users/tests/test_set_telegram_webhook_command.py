from io import StringIO
import traceback
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class SetTelegramWebhookCommandTests(SimpleTestCase):
    @override_settings(
        TELEGRAM_BOT_TOKEN="123:test-bot-token",
        TELEGRAM_WEBHOOK_SECRET="strong_webhook-secret_1234567890",
        SITE_URL="https://mudaroba.com",
    )
    @patch("apps.users.management.commands.set_telegram_webhook.requests.post")
    def test_set_webhook_sends_the_same_secret_checked_by_endpoint(self, post):
        response = MagicMock()
        response.json.return_value = {"ok": True}
        post.return_value = response

        call_command("set_telegram_webhook", stdout=StringIO(), stderr=StringIO())

        post.assert_called_once_with(
            "https://api.telegram.org/bot123:test-bot-token/setWebhook",
            json={
                "url": "https://mudaroba.com/api/users/telegram/webhook/",
                "secret_token": "strong_webhook-secret_1234567890",
            },
            timeout=10,
        )

    @override_settings(
        TELEGRAM_BOT_TOKEN="123:test-bot-token",
        TELEGRAM_WEBHOOK_SECRET="",
        SITE_URL="https://mudaroba.com",
    )
    @patch("apps.users.management.commands.set_telegram_webhook.requests.post")
    def test_set_webhook_fails_closed_without_secret(self, post):
        with self.assertRaisesRegex(CommandError, "TELEGRAM_WEBHOOK_SECRET"):
            call_command("set_telegram_webhook", stdout=StringIO(), stderr=StringIO())

        post.assert_not_called()

    @override_settings(
        TELEGRAM_BOT_TOKEN="123:test-bot-token",
        TELEGRAM_WEBHOOK_SECRET="contains invalid spaces",
        SITE_URL="https://mudaroba.com",
    )
    @patch("apps.users.management.commands.set_telegram_webhook.requests.post")
    def test_set_webhook_rejects_secret_outside_telegram_character_set(self, post):
        with self.assertRaisesRegex(CommandError, "1–256"):
            call_command("set_telegram_webhook", stdout=StringIO(), stderr=StringIO())

        post.assert_not_called()

    @override_settings(
        TELEGRAM_BOT_TOKEN="123:highly-sensitive-bot-token",
        TELEGRAM_WEBHOOK_SECRET="strong_webhook-secret_1234567890",
        SITE_URL="https://mudaroba.com",
    )
    @patch("apps.users.management.commands.set_telegram_webhook.requests.post")
    def test_request_failure_does_not_expose_token_in_error_or_traceback(self, post):
        token = "123:highly-sensitive-bot-token"
        post.side_effect = requests.RequestException(
            f"failed URL https://api.telegram.org/bot{token}/setWebhook"
        )

        try:
            call_command("set_telegram_webhook", stdout=StringIO(), stderr=StringIO())
        except CommandError as exc:
            rendered_traceback = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            self.assertNotIn(token, str(exc))
            self.assertNotIn(token, rendered_traceback)
        else:  # pragma: no cover - defensive assertion
            self.fail("CommandError was not raised")
