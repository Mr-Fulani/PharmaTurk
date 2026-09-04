#!/usr/bin/env python3
"""Keep legacy flake8 debt from growing while allowing incremental cleanup."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence


DEFAULT_MAX_TOTAL = 3030
FLAKE8_LINE = re.compile(r"^(?P<path>.+?):\d+:\d+: (?P<code>[A-Z]\d+)\b")


@dataclasses.dataclass(frozen=True)
class PythonFileChange:
    """A current Python file and the file that supplies its legacy baseline."""

    current_path: str
    base_path: str | None


def _backend_relative(path: str) -> str | None:
    normalized = pathlib.PurePosixPath(path).as_posix()
    prefix = "backend/"
    if not normalized.startswith(prefix):
        return None
    relative = normalized.removeprefix(prefix)
    return relative if relative.endswith(".py") else None


def parse_changed_python_files(raw_diff: bytes) -> list[PythonFileChange]:
    """Parse ``git diff --name-status -z`` into relevant backend changes."""

    tokens = raw_diff.decode("utf-8", errors="surrogateescape").split("\0")
    changes: list[PythonFileChange] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index]
        index += 1

        if status.startswith(("R", "C")):
            old_path, new_path = tokens[index : index + 2]
            index += 2
            current = _backend_relative(new_path)
            if current is None:
                continue
            base = _backend_relative(old_path) if status.startswith("R") else None
            changes.append(PythonFileChange(current, base))
            continue

        path = tokens[index]
        index += 1
        current = _backend_relative(path)
        if current is None or status.startswith("D"):
            continue
        base = None if status.startswith("A") else current
        changes.append(PythonFileChange(current, base))

    return changes


def normalize_flake8_path(raw_path: str, backend_root: pathlib.Path) -> str:
    path = pathlib.Path(raw_path)
    if path.is_absolute():
        try:
            path = path.relative_to(backend_root)
        except ValueError:
            return path.as_posix()
    normalized = path.as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def parse_flake8_counts(output: str, backend_root: pathlib.Path) -> dict[str, int]:
    """Count violations by normalized path, ignoring non-diagnostic output."""

    counts: collections.Counter[str] = collections.Counter()
    for line in output.splitlines():
        match = FLAKE8_LINE.match(line)
        if match:
            counts[normalize_flake8_path(match.group("path"), backend_root)] += 1
    return dict(counts)


def find_regressions(
    changes: Iterable[PythonFileChange],
    current_counts: Mapping[str, int],
    base_counts: Mapping[str, int],
) -> list[str]:
    regressions = []
    for change in changes:
        current = current_counts.get(change.current_path, 0)
        baseline = base_counts.get(change.current_path, 0)
        if current > baseline:
            regressions.append(f"{change.current_path}: {baseline} -> {current}")
    return regressions


def run_command(
    args: Sequence[str],
    *,
    cwd: pathlib.Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def run_flake8(
    backend_root: pathlib.Path,
    *,
    stdin_text: str | None = None,
    display_name: str | None = None,
) -> dict[str, int]:
    args = [
        sys.executable,
        "-m",
        "flake8",
        "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
    ]
    if stdin_text is None:
        args.append(".")
    else:
        args.extend(["--stdin-display-name", display_name or "baseline.py", "-"])

    result = run_command(args, cwd=backend_root, input_text=stdin_text)
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"flake8 failed with exit code {result.returncode}")
    return parse_flake8_counts(result.stdout, backend_root)


def changed_python_files(repo_root: pathlib.Path, base_ref: str) -> list[PythonFileChange]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "-z",
            f"{base_ref}...HEAD",
            "--",
            "backend",
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        raise RuntimeError(f"git diff failed for base {base_ref}")
    return parse_changed_python_files(result.stdout)


def baseline_counts(
    repo_root: pathlib.Path,
    backend_root: pathlib.Path,
    base_ref: str,
    changes: Iterable[PythonFileChange],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in changes:
        if change.base_path is None:
            counts[change.current_path] = 0
            continue
        result = run_command(
            ["git", "show", f"{base_ref}:backend/{change.base_path}"],
            cwd=repo_root,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise RuntimeError(f"cannot read {change.base_path} from {base_ref}")
        lint_counts = run_flake8(
            backend_root,
            stdin_text=result.stdout,
            display_name=change.base_path,
        )
        counts[change.current_path] = sum(lint_counts.values())
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True, help="Git commit used as the baseline")
    parser.add_argument("--max-total", type=int, default=DEFAULT_MAX_TOTAL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent

    changes = changed_python_files(repo_root, args.base_ref)
    current_counts = run_flake8(backend_root)
    current_total = sum(current_counts.values())
    previous_counts = baseline_counts(repo_root, backend_root, args.base_ref, changes)
    regressions = find_regressions(changes, current_counts, previous_counts)

    print(
        f"flake8 quality gate: total={current_total}/{args.max_total}; "
        f"changed_python_files={len(changes)}"
    )
    for regression in regressions:
        print(f"flake8 regression: {regression}", file=sys.stderr)
    if current_total > args.max_total:
        print(
            f"flake8 total budget exceeded: {current_total} > {args.max_total}",
            file=sys.stderr,
        )
    return 1 if regressions or current_total > args.max_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
