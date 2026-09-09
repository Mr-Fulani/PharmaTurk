"""Fail-closed CI scope: only a backend/docs-only diff can omit frontend work."""
import argparse
import subprocess


def frontend_required(paths):
    # Changes to workflow, Compose, release tooling or unknown paths still get
    # the full frontend gate. No labels, commit messages or user skip flags.
    return not paths or any(
        not (path.startswith(("backend/", "docs/")) or path in {"README.md", "DEPLOY.md"})
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
        required = frontend_required(paths)
    except (subprocess.CalledProcessError, UnicodeError):
        required = True
    print(f"frontend={str(required).lower()}")


if __name__ == "__main__":
    main()
