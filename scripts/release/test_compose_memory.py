"""Production Compose memory invariants (OOM incident 2026-10-19).

Runs in the CI compose job, where .env is copied from .env.example.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
# 7.7 GB RAM on the server; leave the OS at least ~0.7 GiB besides swap.
MEMORY_BUDGET_BYTES = 7 * 1024**3
APP_SERVICES = ("backend", "celeryworker", "celery_ai", "celery_recsys", "celerybeat")


def production_services():
    output = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml",
         "config", "--format", "json"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    return json.loads(output)["services"]


def flag(command, name):
    return command[command.index(name) + 1]


@unittest.skipUnless(shutil.which("docker") and (ROOT / ".env").exists(),
                     "needs docker compose and .env")
class ProductionMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services = production_services()

    def test_every_long_running_service_is_capped_within_server_memory(self):
        running = {name: s for name, s in self.services.items() if not s.get("profiles")}
        missing = [name for name, s in running.items() if not s.get("mem_limit")]
        self.assertEqual(missing, [])
        total = sum(int(s["mem_limit"]) for s in running.values())
        self.assertLessEqual(total, MEMORY_BUDGET_BYTES)

    def test_broker_never_evicts_and_cache_evicts(self):
        broker = self.services["redis"]["command"]
        self.assertEqual(flag(broker, "--maxmemory-policy"), "noeviction")
        self.assertIn("--maxmemory", broker)
        self.assertNotIn("--save", broker)  # default RDB snapshots keep queues across recreate

        cache = self.services["redis-cache"]["command"]
        self.assertEqual(flag(cache, "--maxmemory-policy"), "allkeys-lru")
        self.assertIn("--maxmemory", cache)
        self.assertEqual(flag(cache, "--save"), "")
        self.assertNotIn("volumes", self.services["redis-cache"])

    def test_django_cache_lives_outside_the_broker(self):
        for name in APP_SERVICES:
            service = self.services[name]
            self.assertEqual(service["environment"]["REDIS_CACHE_URL"],
                             "redis://redis-cache:6379/0", name)
            self.assertIn("redis-cache", service["depends_on"], name)


if __name__ == "__main__":
    unittest.main()
