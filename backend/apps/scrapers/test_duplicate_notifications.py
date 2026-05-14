from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.scrapers.tasks import (
    _build_duplicate_candidates_notification_text,
    _send_duplicate_candidates_notification,
)


def test_build_duplicate_candidates_notification_text_contains_summary_and_examples(settings):
    settings.SITE_URL = "http://localhost:8000"
    result = {
        "duplicates_found": 3,
        "candidates_created": 2,
        "candidates_updated": 1,
        "duplicates": [
            {
                "canonical_product_name": "Aspirin 500",
                "duplicate_product_name": "Aspirin 500 mg",
                "score": 95.0,
            }
        ],
    }

    text = _build_duplicate_candidates_notification_text(result)

    assert "Всего найдено: 3" in text
    assert "Создано новых: 2" in text
    assert "Обновлено существующих: 1" in text
    assert "Aspirin 500 ↔ Aspirin 500 mg" in text
    assert "/admin/scrapers/productduplicatecandidate/" in text


@override_settings(TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_CHAT_ID="12345", SITE_URL="http://localhost:8000")
def test_send_duplicate_candidates_notification_sends_telegram_message():
    result = {
        "duplicates_found": 2,
        "candidates_created": 2,
        "candidates_updated": 0,
        "duplicates": [],
    }

    response = Mock(ok=True, text="ok")
    with patch("apps.scrapers.tasks.requests.post", return_value=response) as mocked_post:
        sent = _send_duplicate_candidates_notification(result)

    assert sent is True
    mocked_post.assert_called_once()
    payload = mocked_post.call_args.kwargs["json"]
    assert payload["chat_id"] == "12345"
    assert "Найдены кандидаты в дубликаты товаров" in payload["text"]


@override_settings(TELEGRAM_BOT_TOKEN="bot-token", TELEGRAM_CHAT_ID="12345")
def test_send_duplicate_candidates_notification_skips_empty_result():
    result = {
        "duplicates_found": 0,
        "candidates_created": 0,
        "candidates_updated": 0,
        "duplicates": [],
    }

    with patch("apps.scrapers.tasks.requests.post") as mocked_post:
        sent = _send_duplicate_candidates_notification(result)

    assert sent is False
    mocked_post.assert_not_called()


@override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
def test_send_duplicate_candidates_notification_skips_when_telegram_not_configured():
    result = {
        "duplicates_found": 1,
        "candidates_created": 1,
        "candidates_updated": 0,
        "duplicates": [],
    }

    with patch("apps.scrapers.tasks.requests.post") as mocked_post:
        sent = _send_duplicate_candidates_notification(result)

    assert sent is False
    mocked_post.assert_not_called()
