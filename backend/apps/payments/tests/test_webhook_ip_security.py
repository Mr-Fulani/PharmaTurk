from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.payments.views import _verify_webhook_request


class CoinRemitterWebhookIPTests(SimpleTestCase):
    @override_settings(COINREMITTER_WEBHOOK_IP_WHITELIST=["203.0.113.20"])
    def test_uses_nginx_real_ip_and_ignores_forwarded_for(self):
        allowed = SimpleNamespace(
            META={
                "HTTP_X_REAL_IP": "203.0.113.20",
                "HTTP_X_FORWARDED_FOR": "10.0.0.1",
                "REMOTE_ADDR": "172.18.0.3",
            }
        )
        spoofed = SimpleNamespace(
            META={
                "HTTP_X_REAL_IP": "198.51.100.10",
                "HTTP_X_FORWARDED_FOR": "203.0.113.20",
                "REMOTE_ADDR": "172.18.0.3",
            }
        )

        self.assertTrue(_verify_webhook_request(allowed))
        self.assertFalse(_verify_webhook_request(spoofed))

    @override_settings(COINREMITTER_WEBHOOK_IP_WHITELIST=[])
    def test_empty_whitelist_keeps_authenticated_reconciliation_enabled(self):
        request = SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.1"})
        self.assertTrue(_verify_webhook_request(request))
