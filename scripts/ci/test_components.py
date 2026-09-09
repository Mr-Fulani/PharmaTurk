import unittest

from components import frontend_required


class ScopeTests(unittest.TestCase):
    def test_backend_only(self):
        self.assertFalse(frontend_required(["backend/apps/scrapers/tasks.py", "docs/parser.md"]))

    def test_shared_changes_fail_closed(self):
        for path in ["frontend/src/a.ts", "frontend/content/a.md", "frontend/package-lock.json", "docker-compose.yml",
                     ".github/workflows/ci.yml", "scripts/release/deploy.sh", "unknown.txt",
                     "nginx/default.conf", ".env.example"]:
            with self.subTest(path=path):
                self.assertTrue(frontend_required(["backend/a.py", path]))

    def test_empty_diff_is_not_a_skip(self):
        self.assertTrue(frontend_required([]))


if __name__ == "__main__":
    unittest.main()
