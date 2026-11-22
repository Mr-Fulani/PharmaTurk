"""Размер тела запроса и заголовок хоста в nginx (проверка защиты 22.11.2026)."""
from pathlib import Path
import re
import unittest

CONF = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text()


def _location(prefix):
    return CONF.split(prefix, 1)[1].split("\n    }", 1)[0]


class RequestLimitsTests(unittest.TestCase):
    def test_default_body_limit_is_small(self):
        server = CONF.split("server_name mudaroba.com;", 1)[1].split("location", 1)[0]
        self.assertIn("client_max_body_size 12M;", server)

    def test_only_admin_and_feedback_accept_large_bodies(self):
        self.assertEqual(CONF.count("client_max_body_size 100M;"), 1)
        large = _location("location ~ ^/(admin|api/feedback)(/|$) {")
        self.assertIn("client_max_body_size 100M;", large)
        self.assertIn("proxy_pass http://backend_upstream;", large)
        # Блок стоит раньше общего правила /api: у regex-локаций побеждает первая.
        self.assertLess(
            CONF.index("location ~ ^/(admin|api/feedback)(/|$) {"),
            CONF.index("location ~ ^/(admin|api|swagger|redoc) {"),
        )

    def test_client_forwarded_host_is_overwritten_everywhere(self):
        hosts = len(re.findall(r"proxy_set_header Host \$host;", CONF))
        forwarded = len(re.findall(r"proxy_set_header X-Forwarded-Host \$host;", CONF))
        self.assertGreater(hosts, 0)
        self.assertEqual(hosts, forwarded)


if __name__ == "__main__":
    unittest.main()
