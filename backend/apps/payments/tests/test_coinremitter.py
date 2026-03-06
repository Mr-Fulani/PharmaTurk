"""Тесты для CoinRemitter провайдера."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# create_invoice
# ---------------------------------------------------------------------------

class TestCreateInvoice:
    """Тесты функции create_invoice из apps.payments.providers.coinremitter."""

    def _make_create_response(self, invoice_id="inv123", success=True):
        """Вспомогательный: мокаем ответ /invoice/create."""
        return {
            "success": success,
            "data": {
                "id": invoice_id,
                "invoice_id": invoice_id,
                "amount": "1.74",
                "usd_amount": "1.74",
                "expire_on_timestamp": 9999999999000,
                "url": f"https://coinremitter.com/invoice/{invoice_id}",
            },
        }

    def _make_get_response(self, invoice_id="inv123"):
        """Вспомогательный: мокаем ответ /invoice/get (с адресом и QR)."""
        return {
            "success": True,
            "data": {
                "id": invoice_id,
                "invoice_id": invoice_id,
                "amount": "1.74",
                "usd_amount": "1.74",
                "expire_on_timestamp": 9999999999000,
                "url": f"https://coinremitter.com/invoice/{invoice_id}",
                "crypto_currency": [
                    {
                        "address": "TNdummyRealAddress1234567890ABCDEF",
                        "qr_code": "https://qr.example.com/qr.png",
                    }
                ],
            },
        }

    @patch("apps.payments.providers.coinremitter._get_config")
    @patch("requests.post")
    def test_create_invoice_success(self, mock_post, mock_config):
        """Успешное создание инвойса → правильный парс ответа."""
        mock_config.return_value = {
            "api_key": "test_key",
            "api_password": "test_pass",
            "coin": "TCN",
        }
        # requests.post вызывается дважды: create + get
        create_resp = MagicMock()
        create_resp.json.return_value = self._make_create_response()
        get_resp = MagicMock()
        get_resp.json.return_value = self._make_get_response()
        mock_post.side_effect = [create_resp, get_resp]

        from apps.payments.providers.coinremitter import create_invoice

        result = create_invoice(
            amount_fiat=1.74,
            fiat_currency="USD",
            order_number="ABC123",
            notify_url="https://example.com/webhook/",
        )

        assert result is not None
        assert result["address"] == "TNdummyRealAddress1234567890ABCDEF"
        assert result["qr_code"] == "https://qr.example.com/qr.png"
        assert result["amount"] == Decimal("1.74")
        assert result["invoice_id"] == "inv123"
        assert result["invoice_url"] == "https://coinremitter.com/invoice/inv123"

    @patch("apps.payments.providers.coinremitter._get_config")
    def test_create_invoice_no_api_key(self, mock_config):
        """Без API-ключа → возвращаем None без HTTP-запроса."""
        mock_config.return_value = {"api_key": "", "api_password": "", "coin": "TCN"}

        from apps.payments.providers.coinremitter import create_invoice

        result = create_invoice(
            amount_fiat=1.74,
            fiat_currency="USD",
            order_number="ABC123",
            notify_url="",
        )
        assert result is None

    @patch("apps.payments.providers.coinremitter._get_config")
    @patch("requests.post")
    def test_create_invoice_api_error_response(self, mock_post, mock_config):
        """CoinRemitter вернул success=False → None."""
        mock_config.return_value = {
            "api_key": "key",
            "api_password": "pass",
            "coin": "TCN",
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": False, "msg": "Invalid credentials"}
        mock_post.return_value = resp

        from apps.payments.providers.coinremitter import create_invoice

        result = create_invoice(
            amount_fiat=1.74,
            fiat_currency="USD",
            order_number="ABC123",
            notify_url="",
        )
        assert result is None

    @patch("apps.payments.providers.coinremitter._get_config")
    @patch("requests.post")
    def test_create_invoice_network_error(self, mock_post, mock_config):
        """Сетевая ошибка (timeout/connection) → None."""
        import requests as req_lib
        mock_config.return_value = {
            "api_key": "key",
            "api_password": "pass",
            "coin": "TCN",
        }
        mock_post.side_effect = req_lib.exceptions.ConnectionError("timeout")

        from apps.payments.providers.coinremitter import create_invoice

        result = create_invoice(
            amount_fiat=1.74,
            fiat_currency="USD",
            order_number="ABC123",
            notify_url="",
        )
        assert result is None

    @patch("apps.payments.providers.coinremitter._get_config")
    @patch("requests.post")
    def test_create_invoice_localhost_urls_filtered(self, mock_post, mock_config):
        """localhost notify_url/success_url НЕ передаётся в payload (CoinRemitter их не принимает)."""
        mock_config.return_value = {
            "api_key": "key",
            "api_password": "pass",
            "coin": "TCN",
        }
        create_resp = MagicMock()
        create_resp.json.return_value = self._make_create_response()
        get_resp = MagicMock()
        get_resp.json.return_value = self._make_get_response()
        mock_post.side_effect = [create_resp, get_resp]

        from apps.payments.providers.coinremitter import create_invoice

        create_invoice(
            amount_fiat=1.0,
            fiat_currency="USD",
            order_number="XYZ",
            notify_url="http://localhost:8000/webhook/",
            success_url="http://localhost:3000/success",
            fail_url="http://127.0.0.1:3000/fail",
        )

        # Проверяем что в call_args первого вызова нет notify_url/success_url/fail_url
        call_kwargs = mock_post.call_args_list[0]
        payload = call_kwargs[1].get("data") or call_kwargs[0][1]
        assert "notify_url" not in payload
        assert "success_url" not in payload
        assert "fail_url" not in payload
