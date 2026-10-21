"""nginx сам перечитывает адреса backend/frontend: рестарт после деплоя не нужен.

До 15.07.2026 адрес определялся один раз при старте, и пересозданный контейнер с
новым IP давал 502 на все /api до ручного docker restart (docs/PROD_MEMORY.md,
«nginx и новые адреса контейнеров»). Тест держит конфиг, на который опираются доки.
"""
from pathlib import Path
import re
import unittest

CONF = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text()


class NginxRuntimeResolveTests(unittest.TestCase):
    def test_docker_dns_is_reread_every_ten_seconds(self):
        self.assertRegex(CONF, r"(?m)^resolver 127\.0\.0\.11 valid=10s\b")

    def test_upstreams_resolve_container_names_at_runtime(self):
        for name, server in (("backend_upstream", "backend:8000"), ("frontend_upstream", "frontend:3000")):
            block = re.search(rf"upstream {name} \{{(.*?)\}}", CONF, re.S)
            self.assertIsNotNone(block, name)
            self.assertIn(f"zone {name} ", block.group(1))
            self.assertIn(f"server {server} resolve;", block.group(1))

    def test_proxy_pass_goes_only_through_resolving_upstreams(self):
        targets = set(re.findall(r"proxy_pass\s+([^;]+);", CONF))
        self.assertEqual(targets, {"http://backend_upstream", "http://frontend_upstream"})


if __name__ == "__main__":
    unittest.main()
