"""Scoped backend rollout: immutable images, read-only preflight, bounded backup.

Never stops/recreates frontend, Nginx or state services. Rollback switches code,
not schema. Unsupported migrations fail before any backup or service stop.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from pin_versions import pin, pinned_content, sha

WRITERS = ("backend", "celeryworker", "celery_ai", "celery_recsys", "celerybeat")
PRESERVED = ("frontend", "nginx", "postgres", "redis", "qdrant")
SAFE_TABLES = ["scrapers_sitescrapertask", "django_migrations"]


def run(argv, *, env=None, stdin=None, stdout=None):
    return subprocess.run(argv, env=env, input=stdin, stdout=stdout or subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def validate_plan(plan):
    if set(plan) != {"migrations", "tables"}:
        raise ValueError("Unexpected migration gate output")
    if plan["tables"] != (SAFE_TABLES if plan["migrations"] else []):
        raise ValueError("Unexpected scoped backup tables")


class Release:
    def __init__(self, args):
        self.args = args
        self.root = Path(__file__).resolve().parents[2]
        self.env_path = self.root / ".env"
        self.env = dict(os.environ, IMAGE_TAG=args.frontend_release,
                        BACKEND_IMAGE_TAG=args.release_id, RUN_MIGRATIONS="0")
        self.compose = ["docker", "compose", "--project-name", args.project_name,
                        "--project-directory", str(self.root), "-f", str(self.root / "docker-compose.yml"),
                        "-f", str(self.root / "docker-compose.prod.yml")]

    def dc(self, *args):
        return run(self.compose + list(args), env=self.env)

    def runtime(self):
        result = {}
        for service in WRITERS + PRESERVED:
            ids = self.dc("ps", "-a", "-q", service).decode().split()
            if not ids and self.args.mode == "rollback" and service in WRITERS:
                result[service] = {"id": None, "revision": None, "running": False}
                continue
            if len(ids) != 1:
                raise ValueError(f"Expected exactly one existing {service} container")
            info = json.loads(run(["docker", "inspect", ids[0]]))[0]
            result[service] = {
                "id": info["Id"], "image": info["Image"],
                "revision": info["Config"]["Labels"].get("org.opencontainers.image.revision"),
                "running": info["State"]["Running"],
                "healthy": info["State"].get("Health", {}).get("Status", "healthy") == "healthy",
            }
        return result

    def check_images(self):
        for version in {self.args.previous_release, self.args.release_id}:
            data = json.loads(run(["docker", "image", "inspect", f"mudaroba-backend:{version}"]))[0]
            if data["Config"]["Labels"].get("org.opencontainers.image.revision") != version:
                raise ValueError("Backend image SHA mismatch")
            if data["Config"]["User"] != "app":
                raise ValueError("Backend image must use non-root app user")

    def compatibility(self):
        for path in ("frontend", "nginx"):
            old = run(["git", "-C", str(self.root), "rev-parse", f"{self.args.frontend_release}:{path}"])
            new = run(["git", "-C", str(self.root), "rev-parse", f"HEAD:{path}"])
            if old != new:
                raise ValueError(f"{path} changed; use full release")
        # Compare resolved protected service definitions with the deployed
        # revision, using the same .env, project directory and interpolation.
        current = json.loads(self.dc("config", "--format", "json"))["services"]
        with tempfile.TemporaryDirectory(prefix="backend-compose-check-") as tmp:
            files = []
            for name in ("docker-compose.yml", "docker-compose.prod.yml"):
                path = Path(tmp) / name
                write_new(path, run(["git", "-C", str(self.root), "show",
                                     f"{self.args.frontend_release}:{name}"]))
                files.extend(["-f", str(path)])
            command = self.compose[:6] + files + ["config", "--format", "json"]
            previous = json.loads(run(command, env=self.env))["services"]
        for service in PRESERVED:
            if current[service] != previous[service]:
                raise ValueError(f"Protected Compose service {service} changed; use full release")

    def plan(self):
        output = self.dc("--profile", "ops", "run", "--no-deps", "-T", "-e",
                         "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=15000",
                         "migrate", "backend_release_plan")
        plan = json.loads(output)
        validate_plan(plan)
        return plan

    def preflight(self):
        if run(["git", "-C", str(self.root), "status", "--porcelain"]).strip():
            raise ValueError("Release checkout must be clean")
        head = run(["git", "-C", str(self.root), "rev-parse", "HEAD"]).decode().strip()
        if self.args.mode != "rollback" and head != self.args.release_id:
            raise ValueError("Release SHA must match checkout")
        if self.env_path.is_symlink() or self.env_path.stat().st_mode & 0o077:
            raise ValueError("Expected a private regular .env")
        original = self.env_path.read_bytes()
        pinned_content(original, self.args.release_id, self.args.frontend_release)
        self.check_images()
        self.compatibility()
        state = self.runtime()
        checked = PRESERVED if self.args.mode == "rollback" else WRITERS + PRESERVED
        if not all(state[s]["running"] and state[s]["healthy"] for s in checked):
            raise ValueError("All services must be healthy/running before a scoped rollout")
        allowed = {self.args.previous_release}
        if self.args.mode == "rollback":
            allowed.update({self.args.release_id, None})
        if any(state[s]["revision"] not in allowed for s in WRITERS):
            raise ValueError("Current backend/worker SHAs do not match previous-release")
        if state["frontend"]["revision"] != self.args.frontend_release:
            raise ValueError("Current frontend SHA does not match frontend-release")
        return original, state

    def backup(self, original, state, plan):
        root = Path(self.args.backup_root)
        if not root.is_absolute() or str(root) == "/" or root.is_symlink():
            raise ValueError("Use an absolute private non-root backup directory")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="backend-release-", dir=root))
        write_new(directory / "env.backup", original)
        manifest = {
            "format": "mudaroba-backend-release-v1", "previous": self.args.previous_release,
            "release": self.args.release_id, "frontend": self.args.frontend_release,
            "plan": plan, "env_sha256": digest(original),
        }
        if plan["tables"]:
            command = ["docker", "exec", state["postgres"]["id"], "sh", "-ec",
                       'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" '
                       '--format=custom --strict-names '
                       '--table=public.scrapers_sitescrapertask --table=public.django_migrations']
            dump = run(command)
            run(["docker", "exec", "-i", state["postgres"]["id"], "pg_restore", "--list"], stdin=dump)
            write_new(directory / "parser-control.dump", dump)
            manifest["dump_sha256"] = digest(dump)
        write_new(directory / "manifest.json", json.dumps(manifest, sort_keys=True).encode())
        print(f"Protected release record: {directory}", flush=True)
        return directory

    def switch(self, state):
        self.dc("stop", *WRITERS)
        self.dc("up", "-d", "--no-build", "--no-deps", "--wait", "--wait-timeout", "180", *WRITERS)
        after = self.runtime()
        if any(after[s] != state[s] for s in PRESERVED):
            raise ValueError("Protected service identity changed")
        if any(after[s]["revision"] != self.args.release_id or not after[s]["running"] or not after[s]["healthy"] for s in WRITERS):
            raise ValueError("New backend/worker versions are inconsistent")
        run(["bash", str(self.root / "scripts/release/postdeploy-smoke.sh"),
             "--base-url", self.args.base_url])

    def execute(self):
        original, state = self.preflight()
        if self.args.mode == "rollback":
            directory = Path(self.args.receipt)
            manifest = json.loads((directory / "manifest.json").read_bytes())
            if (manifest.get("format"), manifest.get("previous"), manifest.get("release"), manifest.get("frontend")) != (
                "mudaroba-backend-release-v1", self.args.release_id, self.args.previous_release, self.args.frontend_release,
            ):
                raise ValueError("Rollback receipt does not match the exact component versions")
            if digest((directory / "env.backup").read_bytes()) != manifest["env_sha256"]:
                raise ValueError("Rollback environment backup checksum mismatch")
            validate_plan(manifest["plan"])
            if manifest["plan"]["tables"] and digest((directory / "parser-control.dump").read_bytes()) != manifest["dump_sha256"]:
                raise ValueError("Scoped dump checksum mismatch")
            self.switch(state)
        else:
            plan = self.plan()
            print(json.dumps({"preflight": "passed", **plan}), flush=True)
            if self.args.mode == "check":
                return
            directory = self.backup(original, state, plan)
            # Only additive nullable control fields are allowed. Apply while
            # the old code still serves traffic; bound locks and total duration.
            if plan["migrations"]:
                if self.plan() != plan:
                    raise ValueError("Migration plan changed after backup")
                self.dc("--profile", "ops", "run", "--no-deps", "-T", "-e",
                        "PGOPTIONS=-c lock_timeout=3000 -c statement_timeout=30000",
                        "migrate", "migrate", "--noinput")
            self.switch(state)
        if self.env_path.read_bytes() != original:
            raise ValueError(".env changed during deployment; not overwriting it")
        pin(self.env_path, self.args.release_id, self.args.frontend_release)
        write_new(directory / f"{self.args.mode}-completed.json", json.dumps({
            "backend": self.args.release_id, "frontend": self.args.frontend_release,
        }).encode())
        print(f"{self.args.mode} complete: backend={self.args.release_id}, frontend unchanged", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["check", "deploy", "rollback"], default="check")
    parser.add_argument("--release-id", type=sha, required=True)
    parser.add_argument("--previous-release", type=sha, required=True)
    parser.add_argument("--frontend-release", type=sha, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--backup-root")
    parser.add_argument("--receipt")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", args.project_name):
        parser.error("Invalid project name")
    if not re.fullmatch(r"https://[^/]+", args.base_url):
        parser.error("Expected public HTTPS origin")
    if args.release_id == args.previous_release:
        parser.error("Target and previous backend SHAs must differ")
    if args.mode != "check" and args.confirm != f"{args.mode.upper()} BACKEND {args.release_id}":
        parser.error("Exact backend operation/SHA confirmation required")
    if args.mode == "deploy" and not args.backup_root:
        parser.error("Deploy requires --backup-root")
    if args.mode == "rollback" and not args.receipt:
        parser.error("Rollback requires the matching --receipt directory")
    try:
        Release(args).execute()
    except subprocess.CalledProcessError as exc:
        # Never echo captured Compose/inspect/environment output.
        raise SystemExit(f"Release command failed (exit {exc.returncode}); services may need the documented rollback") from None


if __name__ == "__main__":
    main()
