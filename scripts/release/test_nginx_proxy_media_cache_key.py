"""Ключ кэша proxy-media собран только из параметров, которые читает бэкенд.

Со всей строкой запроса в ключе любой лишний параметр (?x=1) давал промах: чтение
из R2 и пересжатие той же картинки в рабочем процессе gunicorn.
"""
from pathlib import Path
import unittest

CONF = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text()


class ProxyMediaCacheKeyTests(unittest.TestCase):
    def test_cache_key_ignores_unknown_query_parameters(self):
        location = CONF.split("location ^~ /api/catalog/proxy-media", 1)[1].split("\n    }", 1)[0]
        key_line = next(line for line in location.splitlines() if "proxy_cache_key" in line)

        self.assertNotIn("$args", key_line)
        for variable in ("$arg_path", "$arg_max_width", "$arg_w", "$arg_format", "$accept_webp"):
            self.assertIn(variable, key_line)


if __name__ == "__main__":
    unittest.main()
