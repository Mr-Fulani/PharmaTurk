import hashlib
import hmac
import re
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.users.telegram_auth import (
    TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS,
    _send_telegram_message,
    generate_telegram_sync_token,
    process_telegram_webhook,
    validate_telegram_data,
    validate_telegram_sync_token,
)


def _signed_widget_payload(auth_date) -> dict:
    payload = {
        "id": "123456",
        "first_name": "Buyer",
        "auth_date": str(auth_date),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret = hashlib.sha256(b"test-bot-token").digest()
    payload["hash"] = hmac.new(
        secret,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return payload


class TelegramWidgetValidationTests(SimpleTestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="test-bot-token")
    def test_recent_signed_payload_is_accepted(self):
        self.assertTrue(validate_telegram_data(_signed_widget_payload(int(time.time()))))

    @override_settings(TELEGRAM_BOT_TOKEN="test-bot-token")
    def test_stale_future_and_malformed_dates_are_rejected(self):
        invalid_dates = [
            int(time.time()) - 86401,
            int(time.time()) + 61,
            "not-a-timestamp",
        ]
        for auth_date in invalid_dates:
            with self.subTest(auth_date=auth_date):
                self.assertFalse(validate_telegram_data(_signed_widget_payload(auth_date)))


class TelegramSyncTokenSecurityTests(SimpleTestCase):
    @patch("apps.users.telegram_auth.time.time", return_value=1_800_000_000)
    def test_generated_token_is_deep_link_safe_signed_and_time_limited(self, _time):
        user = SimpleNamespace(telegram_sync_token=None)
        user.save = lambda **kwargs: None

        token = generate_telegram_sync_token(user)

        self.assertEqual(user.telegram_sync_token, token)
        self.assertLessEqual(len(token), 64)
        self.assertRegex(token, re.compile(r"^[A-Za-z0-9_-]+$"))
        self.assertTrue(validate_telegram_sync_token(token, now=1_800_000_000))
        self.assertTrue(
            validate_telegram_sync_token(
                token,
                now=1_800_000_000 + TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS,
            )
        )
        self.assertFalse(
            validate_telegram_sync_token(
                token,
                now=1_800_000_001 + TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS,
            )
        )

    @patch("apps.users.telegram_auth.time.time", return_value=1_800_000_000)
    def test_tampered_and_far_future_tokens_are_rejected(self, _time):
        user = SimpleNamespace(telegram_sync_token=None, save=lambda **kwargs: None)
        token = generate_telegram_sync_token(user)

        replacement = "0" if token[-1] != "0" else "1"
        self.assertFalse(validate_telegram_sync_token(token[:-1] + replacement))
        self.assertFalse(validate_telegram_sync_token(token, now=1_799_999_939))

    @patch("apps.users.telegram_auth._send_telegram_message")
    @patch("apps.users.telegram_auth.User.objects.filter")
    def test_webhook_rejects_and_clears_expired_stored_token(self, user_filter, _send):
        user = SimpleNamespace(telegram_sync_token=None, save=lambda **kwargs: None)
        with patch("apps.users.telegram_auth.time.time", return_value=1_800_000_000):
            token = generate_telegram_sync_token(user)

        payload = {
            "message": {
                "text": f"/start {token}",
                "from": {"id": 123456},
                "chat": {"id": 123456, "type": "private"},
            }
        }
        with patch(
            "apps.users.telegram_auth.time.time",
            return_value=1_800_000_001 + TELEGRAM_SYNC_TOKEN_MAX_AGE_SECONDS,
        ):
            self.assertFalse(process_telegram_webhook(payload))

        user_filter.assert_called_once_with(telegram_sync_token=token)
        user_filter.return_value.update.assert_called_once_with(telegram_sync_token=None)


class TelegramWebhookLoggingTests(SimpleTestCase):
    @patch("apps.users.telegram_auth._send_telegram_message")
    @patch("apps.users.telegram_auth.User.objects.filter")
    @patch("apps.users.telegram_auth.logger")
    def test_invalid_one_time_token_is_never_written_to_logs(
        self, logger, user_filter, _send_message
    ):
        user_filter.return_value.first.return_value = None
        raw_token = "high-entropy-one-time-secret"

        self.assertFalse(
            process_telegram_webhook(
                {
                    "message": {
                        "text": f"/start {raw_token}",
                        "from": {"id": 123456},
                        "chat": {"id": 123456, "type": "private"},
                    }
                }
            )
        )

        self.assertNotIn(raw_token, str(logger.method_calls))

    @override_settings(TELEGRAM_BOT_TOKEN="123:highly-sensitive-bot-token")
    @patch("apps.users.telegram_auth.logger")
    @patch("requests.post")
    def test_send_error_never_logs_requests_exception_containing_bot_token(
        self, post, logger
    ):
        token = "123:highly-sensitive-bot-token"
        post.side_effect = RuntimeError(
            f"failed URL https://api.telegram.org/bot{token}/sendMessage"
        )

        _send_telegram_message(123456, "test")

        self.assertNotIn(token, str(logger.method_calls))
