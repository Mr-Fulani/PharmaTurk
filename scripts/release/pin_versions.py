"""Atomically pin component SHAs while preserving every other .env byte."""
import argparse
import os
from pathlib import Path
import re
import stat
import tempfile


def sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Component versions must be full Git SHAs")
    return value


def pinned_content(raw, backend, frontend):
    values = {"BACKEND_IMAGE_TAG": sha(backend), "IMAGE_TAG": sha(frontend)}
    lines = raw.splitlines(keepends=True)
    for key, value in values.items():
        found = [i for i, line in enumerate(lines) if re.match(rb"\s*(?:export\s+)?" + key.encode() + rb"\s*=", line)]
        if len(found) > 1:
            raise ValueError("Duplicate component version setting")
        replacement = f"{key}={value}\n".encode()
        if found:
            ending = b"\r\n" if lines[found[0]].endswith(b"\r\n") else b"\n"
            lines[found[0]] = replacement.rstrip(b"\n") + ending
        else:
            if lines and not lines[-1].endswith(b"\n"):
                lines[-1] += b"\n"
            lines.append(replacement)
    return b"".join(lines)


def pin(path, backend, frontend):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Environment must be a real regular file")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("Environment must not be group/world accessible")
    original = path.read_bytes()
    updated = pinned_content(original, backend, frontend)
    if original == updated:
        return
    descriptor, pending = tempfile.mkstemp(prefix=".release-env-", dir=path.parent)
    with os.fdopen(descriptor, "wb") as output:
        os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
        os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
        output.write(updated)
        output.flush()
        os.fsync(output.fileno())
    if path.is_symlink() or path.read_bytes() != original:
        raise ValueError("Environment changed concurrently; protected pending file retained")
    os.replace(pending, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--frontend", required=True)
    args = parser.parse_args()
    pin(args.env, args.backend, args.frontend)
