"""Fail-closed CI scope: independent application checks; shared/unknown changes run both."""
import argparse
import subprocess


def frontend_required(paths):
    # Changes to workflow, Compose, release tooling or unknown paths still get
    # the full frontend gate. No labels, commit messages or user skip flags.
    return not paths or any(
        not (path.startswith(("backend/", "docs/")) or path in {"README.md", "DEPLOY.md"})
        for path in paths
    )


def backend_required(paths):
    # Only a diff containing frontend changes and optional documentation can
    # omit backend functional tests/build. Docs-only retains the existing gate.
    return not any(path.startswith("frontend/") for path in paths) or any(
        not (path.startswith(("frontend/", "docs/")) or path in {"README.md", "DEPLOY.md"})
        for path in paths
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    try:
        subprocess.run(["git", "cat-file", "-e", f"{args.base}^{{commit}}"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = subprocess.check_output([
            "git", "diff", "--name-only", "--no-renames", "-z", args.base, "HEAD",
        ])
        paths = raw.decode().strip("\0").split("\0") if raw else []
        frontend = frontend_required(paths)
        backend = backend_required(paths)
    except (subprocess.CalledProcessError, UnicodeError):
        frontend = backend = True
    print(f"frontend={str(frontend).lower()}")
    print(f"backend={str(backend).lower()}")


if __name__ == "__main__":
    main()
