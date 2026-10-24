"""TD-018: refresh-токен живёт только в HttpOnly cookie."""

import json
import logging
from unittest.mock import patch

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.auth_cookies import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from apps.users.models import User

REFRESH_URL = "/api/auth/jwt/refresh/"
LOGIN_URL = "/api/users/login/"
LOGOUT_URL = "/api/auth/logout/"
TELEGRAM_URL = "/api/users/telegram/login/"


class RefreshCookieTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="cookie@example.com",
            username="cookie_user",
            password="Str0ng-pass-for-tests",
        )

    def _assert_http_only_refresh_cookie(self, response):
        cookie = response.cookies[REFRESH_COOKIE_NAME]
        self.assertTrue(cookie.value)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], REFRESH_COOKIE_PATH)
        # Без Max-Age, как прежние cookie фронта: закрытие браузера = выход.
        self.assertEqual(cookie["max-age"], "")
        return cookie.value

    def test_login_sets_http_only_cookie_and_hides_refresh_from_body(self):
        response = self.client.post(
            LOGIN_URL,
            {"email": "cookie@example.com", "password": "Str0ng-pass-for-tests"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["tokens"])
        self.assertNotIn("refresh", response.data["tokens"])
        refresh = self._assert_http_only_refresh_cookie(response)
        RefreshToken(refresh)  # валидный токен

    @patch("apps.users.telegram_auth.validate_telegram_data", return_value=True)
    def test_telegram_login_sets_http_only_cookie(self, _validate):
        self.user.telegram_id = "555000111"
        self.user.save(update_fields=["telegram_id"])

        response = self.client.post(TELEGRAM_URL, {"id": "555000111"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("refresh", response.data["tokens"])
        self._assert_http_only_refresh_cookie(response)

    def test_refresh_reads_cookie_rotates_it_and_keeps_body_without_refresh(self):
        old_refresh = str(RefreshToken.for_user(self.user))
        self.client.cookies[REFRESH_COOKIE_NAME] = old_refresh

        response = self.client.post(REFRESH_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        new_refresh = self._assert_http_only_refresh_cookie(response)
        self.assertNotEqual(new_refresh, old_refresh)
        # Ротация с чёрным списком: старый refresh повторно не сработает.
        self.client.cookies[REFRESH_COOKIE_NAME] = old_refresh
        reused = self.client.post(REFRESH_URL, {}, format="json")
        self.assertEqual(reused.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_legacy_body_refresh_still_works_and_moves_session_to_cookie(self):
        # Сессии до релиза: refresh лежал в обычной cookie и приходит в теле.
        legacy_refresh = str(RefreshToken.for_user(self.user))

        response = self.client.post(REFRESH_URL, {"refresh": legacy_refresh}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self._assert_http_only_refresh_cookie(response)

    def test_invalid_or_missing_refresh_is_401_and_clears_cookie(self):
        self.client.cookies[REFRESH_COOKIE_NAME] = "not-a-token"
        response = self.client.post(REFRESH_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, "")

        self.client.cookies.clear()
        response = self.client.post(REFRESH_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_cookie_refresh_and_clears_cookie_without_access(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies[REFRESH_COOKIE_NAME] = str(refresh)

        # Access истёк или не передан — выход всё равно гасит refresh.
        response = self.client.post(LOGOUT_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, "")
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())

    def test_logout_with_broken_refresh_still_succeeds(self):
        self.client.cookies[REFRESH_COOKIE_NAME] = "broken"

        response = self.client.post(LOGOUT_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CspReportTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_report_uri_payload_is_logged_without_query_string(self):
        body = {
            "csp-report": {
                "document-uri": "https://mudaroba.com/cart?email=a@b.c",
                "effective-directive": "script-src-elem",
                "blocked-uri": "https://evil.example/x.js?token=secret",
            }
        }
        with self.assertLogs("csp", level=logging.WARNING) as logs:
            response = self.client.post(
                "/api/csp-report/",
                data=json.dumps(body),
                content_type="application/csp-report",
            )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        line = logs.output[0]
        self.assertIn("script-src-elem", line)
        self.assertIn("https://evil.example/x.js", line)
        self.assertNotIn("secret", line)
        self.assertNotIn("email=", line)

    def test_reporting_api_payload_and_garbage_are_accepted(self):
        body = [
            {
                "type": "csp-violation",
                "body": {
                    "documentURL": "https://mudaroba.com/",
                    "effectiveDirective": "img-src",
                    "blockedURL": "https://img.example/a.png",
                },
            }
        ]
        with self.assertLogs("csp", level=logging.WARNING):
            response = self.client.post(
                "/api/csp-report/",
                data=json.dumps(body),
                content_type="application/reports+json",
            )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.post(
            "/api/csp-report/", data="not json", content_type="text/plain"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
