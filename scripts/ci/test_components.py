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


class BackendScopeTests(unittest.TestCase):
    def test_frontend_only_including_assets_and_dependencies(self):
        from components import backend_required
        for path in ['frontend/src/pages/index.tsx', 'frontend/public/logo.svg',
                     'frontend/styles/globals.css', 'frontend/package-lock.json',
                     'frontend/Dockerfile']:
            with self.subTest(path=path):
                self.assertFalse(backend_required([path, 'docs/frontend.md', 'README.md']))
                self.assertTrue(frontend_required([path]))

    def test_shared_or_backend_changes_run_both(self):
        from components import backend_required
        for path in ['backend/apps/catalog/views.py', 'backend/poetry.lock',
                     '.github/workflows/ci.yml', 'scripts/ci/components.py',
                     'scripts/release/deploy.sh', 'docker-compose.yml',
                     'nginx/default.conf', '.env.example', 'contracts/api.json',
                     'unknown.txt']:
            with self.subTest(path=path):
                paths = ['frontend/src/pages/index.tsx', path]
                self.assertTrue(backend_required(paths))
                self.assertTrue(frontend_required(paths))

    def test_docs_only_and_empty_diff_keep_backend_gate(self):
        from components import backend_required
        for paths in [[], ['docs/release.md'], ['README.md']]:
            with self.subTest(paths=paths):
                self.assertTrue(backend_required(paths))

    def test_unknown_base_runs_both(self):
        import subprocess
        from pathlib import Path
        script = Path(__file__).with_name('components.py')
        result = subprocess.run(['python3', str(script), '--base', 'missing-ci-base'],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, 'frontend=true\nbackend=true\n')


if __name__ == "__main__":
    unittest.main()
