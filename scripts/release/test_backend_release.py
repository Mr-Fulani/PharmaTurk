import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend_release import PRESERVED, WRITERS, Release, digest, validate_plan
from pin_versions import pin, pinned_content

A, B, C = "a" * 40, "b" * 40, "c" * 40


class PinTests(unittest.TestCase):
    def test_preserves_every_non_version_byte(self):
        raw = b'# comment\r\nTOKEN="secret=value"\r\nIMAGE_TAG=' + A.encode() + b'\r\nFLAG=true\r\n'
        updated = pinned_content(raw, B, C)
        self.assertIn(b'TOKEN="secret=value"\r\n', updated)
        self.assertIn(b'FLAG=true\r\n', updated)
        self.assertIn(f'IMAGE_TAG={C}\r\n'.encode(), updated)
        self.assertTrue(updated.endswith(f'BACKEND_IMAGE_TAG={B}\n'.encode()))

    def test_duplicates_and_non_sha_rejected(self):
        for raw in [b"IMAGE_TAG=x\nIMAGE_TAG=y\n", b"BACKEND_IMAGE_TAG=x\nexport BACKEND_IMAGE_TAG=y\n"]:
            with self.assertRaises(ValueError):
                pinned_content(raw, A, B)
        with self.assertRaises(ValueError):
            pinned_content(b"", "latest", B)

    def test_atomic_file_pin_is_private_idempotent_and_preserves_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_bytes(b"SECRET=keep\nIMAGE_TAG=" + A.encode() + b"\n")
            path.chmod(0o600)
            owner = path.stat().st_uid
            pin(path, B, A)
            expected, inode = path.read_bytes(), path.stat().st_ino
            pin(path, B, A)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_uid, owner)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                pin(link, C, A)


def release(mode="deploy", tmp=None):
    args = argparse.Namespace(mode=mode, release_id=B, previous_release=A,
                              frontend_release=C, project_name="test", base_url="https://example.com",
                              backup_root=tmp, receipt=tmp)
    instance = Release(args)
    if tmp:
        instance.root = Path(tmp)
        instance.env_path = Path(tmp) / ".env"
        instance.env_path.write_bytes(b"SECRET=preserved\n")
        instance.env_path.chmod(0o600)
    return instance


def state(version=A):
    return {s: {"id": s, "revision": version if s in WRITERS else C,
                "running": True, "healthy": True} for s in WRITERS + PRESERVED}


class ReleaseTests(unittest.TestCase):
    def test_migration_gate_cannot_expand_backup_scope(self):
        validate_plan({"migrations": [], "tables": []})
        with self.assertRaises(ValueError):
            validate_plan({"migrations": [["catalog", "x"]], "tables": ["catalog_product"]})

    def test_rollout_never_stops_or_starts_protected_services(self):
        r = release()
        r.dc = Mock()
        before, after = state(), state(B)
        r.runtime = Mock(return_value=after)
        with patch("backend_release.run"):
            r.switch(before)
        self.assertEqual(r.dc.call_args_list[0].args, ("stop", *WRITERS))
        self.assertEqual(r.dc.call_args_list[1].args[-len(WRITERS):], WRITERS)
        for call in r.dc.call_args_list:
            self.assertFalse(set(call.args) & set(PRESERVED))
            self.assertIn("--no-deps", call.args) if call.args[0] == "up" else None

    def test_protected_container_change_aborts_verification(self):
        r = release()
        r.dc = Mock()
        before, after = state(), state(B)
        after["frontend"]["id"] = "recreated"
        r.runtime = Mock(return_value=after)
        with self.assertRaises(ValueError):
            r.switch(before)

    def test_check_and_rejected_plan_never_backup_or_stop_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release("check", tmp)
            r.preflight = Mock(return_value=(r.env_path.read_bytes(), state()))
            r.plan = Mock(return_value={"migrations": [], "tables": []})
            r.backup, r.switch = Mock(), Mock()
            r.execute()
            r.backup.assert_not_called()
            r.switch.assert_not_called()
            r.args.mode = "deploy"
            r.plan.side_effect = ValueError("unsupported migration")
            with self.assertRaises(ValueError):
                r.execute()
            r.backup.assert_not_called()
            r.switch.assert_not_called()

    def test_code_only_deploy_does_not_run_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release(tmp=tmp)
            r.preflight = Mock(return_value=(r.env_path.read_bytes(), state()))
            r.plan = Mock(return_value={"migrations": [], "tables": []})
            r.backup = Mock(return_value=Path(tmp))
            r.switch, r.dc = Mock(), Mock()
            r.execute()
            r.dc.assert_not_called()
            self.assertTrue((Path(tmp) / "deploy-completed.json").exists())

    def test_migration_runs_after_backup_with_bounded_lock_before_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release(tmp=tmp)
            order = []
            r.preflight = Mock(return_value=(r.env_path.read_bytes(), state()))
            r.plan = Mock(return_value={"migrations": [["scrapers", "x"]],
                                       "tables": ["scrapers_sitescrapertask", "django_migrations"]})
            r.backup = Mock(side_effect=lambda *a: order.append("backup") or Path(tmp))
            r.dc = Mock(side_effect=lambda *a: order.append(a))
            r.switch = Mock(side_effect=lambda *a: order.append("switch"))
            r.execute()
            self.assertEqual(order[0], "backup")
            self.assertEqual(order[-1], "switch")
            self.assertIn("PGOPTIONS=-c lock_timeout=3000 -c statement_timeout=30000", order[1])

    def test_failure_does_not_pin_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release(tmp=tmp)
            original = r.env_path.read_bytes()
            r.preflight = Mock(return_value=(original, state()))
            r.plan = Mock(return_value={"migrations": [], "tables": []})
            r.backup = Mock(return_value=Path(tmp))
            r.switch = Mock(side_effect=ValueError("health failed"))
            with self.assertRaises(ValueError):
                r.execute()
            self.assertEqual(r.env_path.read_bytes(), original)

    def test_backup_is_exact_tables_or_env_only_never_qdrant(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release(tmp=tmp)
            plan = {"migrations": [["scrapers", "x"]],
                    "tables": ["scrapers_sitescrapertask", "django_migrations"]}
            with patch("backend_release.run", return_value=b"custom-dump") as command:
                directory = r.backup(b"SECRET=keep", state(), plan)
            self.assertEqual(command.call_count, 2)
            calls = str(command.call_args_list)
            self.assertIn("--table=public.scrapers_sitescrapertask", calls)
            self.assertNotIn("qdrant", calls)
            self.assertEqual((directory / "manifest.json").stat().st_mode & 0o777, 0o600)
            with patch("backend_release.run") as command:
                directory = r.backup(b"SECRET=keep", state(), {"migrations": [], "tables": []})
            command.assert_not_called()
            self.assertFalse((directory / "parser-control.dump").exists())

    def test_rollback_accepts_stopped_and_partially_replaced_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release("rollback", tmp)
            r.check_images, r.compatibility = Mock(), Mock()
            mixed = state()
            mixed["backend"].update(revision=None, running=False, healthy=False)
            mixed["celeryworker"]["revision"] = B
            r.runtime = Mock(return_value=mixed)
            with patch("backend_release.run", return_value=b""):
                r.preflight()
            r.args.mode = "deploy"
            with patch("backend_release.run", side_effect=lambda argv: B.encode() if argv[-1] == "HEAD" else b""):
                with self.assertRaisesRegex(ValueError, "running"):
                    r.preflight()

    def test_rollback_requires_matching_receipt_and_never_migrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release("rollback", tmp)
            original = r.env_path.read_bytes()
            r.preflight = Mock(return_value=(original, state()))
            r.switch, r.dc, r.plan = Mock(), Mock(), Mock()
            (Path(tmp) / "env.backup").write_bytes(original)
            manifest = {"format": "mudaroba-backend-release-v1", "previous": B,
                        "release": A, "frontend": C, "plan": {"migrations": [], "tables": []},
                        "env_sha256": "invalid"}
            (Path(tmp) / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                r.execute()
            r.switch.assert_not_called()
            manifest["env_sha256"] = digest(original)
            (Path(tmp) / "manifest.json").write_text(json.dumps(manifest))
            r.execute()
            r.switch.assert_called_once()
            r.dc.assert_not_called()
            r.plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
