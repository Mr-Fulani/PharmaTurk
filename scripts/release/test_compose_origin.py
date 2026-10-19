"""Origin exposure invariants: only nginx is published, IPv4 only, TLS mount.

Runs in the CI compose job, where .env is copied from .env.example.
"""
from pathlib import Path
import shutil
import unittest

from test_compose_memory import ROOT, production_services


@unittest.skipUnless(shutil.which("docker") and (ROOT / ".env").exists(),
                     "needs docker compose and .env")
class ProductionOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services = production_services()

    def test_only_nginx_publishes_ports(self):
        published = sorted(name for name, s in self.services.items() if s.get("ports"))
        self.assertEqual(published, ["nginx"])

    def test_nginx_is_published_on_ipv4_only(self):
        # [::] goes through docker-proxy: nginx sees the bridge gateway (trusted
        # private range) instead of the client and the Cloudflare gate is open.
        ports = {(p["host_ip"], str(p["published"]), p["target"])
                 for p in self.services["nginx"]["ports"]}
        self.assertEqual(ports, {("0.0.0.0", "80", 80), ("0.0.0.0", "443", 443)})

    def test_origin_tls_directory_is_mounted_read_only(self):
        mounts = {v["target"]: v for v in self.services["nginx"]["volumes"]}
        tls = mounts["/etc/nginx/tls"]
        self.assertTrue(tls["read_only"])
        self.assertEqual(Path(tls["source"]), ROOT / "nginx" / "tls")


if __name__ == "__main__":
    unittest.main()
