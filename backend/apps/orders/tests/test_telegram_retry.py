"""Сбой Telegram: менеджер получает сообщение с повтора, покупатель не получает дублей."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from apps.orders.tasks import (
    TelegramTemporaryError,
    _post_telegram,
    notify_new_order_telegram,
    notify_sourcing_request_telegram,
)
from apps.orders.tests.test_request_telegram_notification import _order

ADMIN = "admin-chat"
CUSTOMER = "555"
# Так выглядит текст настоящей ошибки requests: в адресе запроса токен бота
NETWORK_ERROR = requests.ConnectionError("Max retries exceeded with url: /bottest-token/sendMessage")


def _telegram(post, **scripts):
    """Подменяет Telegram: по чату — очередь ответов, потом всегда 200."""

    def reply(url, **kwargs):
        chat_id = (kwargs.get("json") or kwargs.get("data"))["chat_id"]
        outcome = scripts.get(chat_id, [])
        step = outcome.pop(0) if outcome else 200
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(status_code=step, ok=step < 400)

    post.side_effect = reply


def _sent_to(post):
    return Counter(call.kwargs["json"]["chat_id"] for call in post.call_args_list)


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID=ADMIN)
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.orders.tasks.requests.post")
@patch("apps.orders.models.Order.objects.select_related")
class NewOrderTelegramRetryTests(SimpleTestCase):
    def _run(self, select_related):
        select_related.return_value.get.return_value = _order()
        # apply() выполняет и повторы, сразу и в этом же процессе
        return notify_new_order_telegram.apply(kwargs={"order_id": 9})

    def _assert_manager_survives(self, select_related, post, failure):
        _telegram(post, **{ADMIN: [failure]})

        self._run(select_related)

        self.assertEqual(_sent_to(post), {ADMIN: 2, CUSTOMER: 1})

    def test_network_failure_is_retried_without_customer_duplicate(self, select_related, post, *_):
        self._assert_manager_survives(select_related, post, NETWORK_ERROR)

    def test_telegram_server_error_is_retried_without_customer_duplicate(self, select_related, post, *_):
        self._assert_manager_survives(select_related, post, 503)

    def test_telegram_rate_limit_is_retried_without_customer_duplicate(self, select_related, post, *_):
        self._assert_manager_survives(select_related, post, 429)

    def test_customer_failure_does_not_retry_or_duplicate_manager(self, select_related, post, *_):
        _telegram(post, **{CUSTOMER: [NETWORK_ERROR]})

        self._run(select_related)

        self.assertEqual(_sent_to(post), {ADMIN: 1, CUSTOMER: 1})

    def test_permanent_telegram_error_is_not_retried(self, select_related, post, *_):
        _telegram(post, **{ADMIN: [403]})

        self._run(select_related)

        self.assertEqual(_sent_to(post), {ADMIN: 1, CUSTOMER: 1})

    def test_retries_stop_at_limit_and_task_fails(self, select_related, post, *_):
        _telegram(post, **{ADMIN: [503] * 100})

        with self.assertRaises(TelegramTemporaryError):
            self._run(select_related).get()

        self.assertEqual(
            _sent_to(post),
            {ADMIN: 1 + notify_new_order_telegram.max_retries, CUSTOMER: 1},
        )


class TelegramErrorTextTests(SimpleTestCase):
    @patch("apps.orders.tasks.requests.post", side_effect=NETWORK_ERROR)
    def test_bot_token_does_not_reach_the_log(self, _post):
        with self.assertRaises(TelegramTemporaryError) as caught:
            _post_telegram("test-token", "sendMessage", json={}, timeout=1)

        self.assertNotIn("test-token", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID=ADMIN)
@patch("apps.orders.tasks.requests.post")
@patch("apps.orders.models.SourcingRequest.objects.get")
class SourcingRequestTelegramRetryTests(SimpleTestCase):
    def _run(self, get_request):
        get_request.return_value = SimpleNamespace(
            pk=4,
            source_url="https://example.com/item",
            comment="",
            quantity=1,
            contact_name="Анна",
            contact_phone="+79990001122",
            contact_email="",
            contact_channel="whatsapp",
            contact_username="",
            image=None,
        )
        return notify_sourcing_request_telegram.apply(args=[4])

    def test_network_failure_is_retried(self, get_request, post):
        _telegram(post, **{ADMIN: [NETWORK_ERROR]})

        self._run(get_request)

        self.assertEqual(_sent_to(post), {ADMIN: 2})

    def test_telegram_server_error_is_retried(self, get_request, post):
        _telegram(post, **{ADMIN: [503]})

        self._run(get_request)

        self.assertEqual(_sent_to(post), {ADMIN: 2})

    def test_permanent_telegram_error_is_not_retried(self, get_request, post):
        _telegram(post, **{ADMIN: [403]})

        self._run(get_request)

        self.assertEqual(_sent_to(post), {ADMIN: 1})
