#!/usr/bin/env python3
"""Build TG:BTC Game Assistant v7.3.0 from the exact published v7.2.2 source."""
import argparse
import hashlib
import os
import py_compile
import subprocess
import sys
from pathlib import Path

from arena_v2_patch import apply_arena_v2_patch
from arena_v2_pilot_patch import apply_arena_v2_pilot_patch
from daily_v73_patch import apply_daily_v73_patch
from arena_v2_perception_core import apply_arena_perception_core_patch
from arena_v2_perception_integration import apply_arena_perception_integration_patch
from arena_v2_perception_events import apply_arena_perception_events_patch

BASE_VERSION = "7.2.2"
TARGET_VERSION = "7.3.0"
BASE_SHA256 = "0f20427e63011263cf9c7bacb4d3e604175cd00dac29f218fecda665cc56f289"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    version = str(args.version).strip().lstrip("vV")
    if version != TARGET_VERSION:
        raise SystemExit(f"This builder only produces {TARGET_VERSION}, got {version}")

    repo_root = Path(args.repo_root).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".v722base")

    env = dict(os.environ)
    env["TG_SKIP_MANIFEST_PUBLISH"] = "1"
    subprocess.run([
        sys.executable,
        str(repo_root / "release_payload" / "build_release.py"),
        "--repo-root", str(repo_root),
        "--version", BASE_VERSION,
        "--output", str(temp),
    ], cwd=str(repo_root), env=env, check=True)

    raw = temp.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != BASE_SHA256:
        raise SystemExit(f"v{BASE_VERSION} checksum mismatch: {got}")

    text = raw.decode("utf-8")
    old_version = f'APP_VERSION = "{BASE_VERSION}"'
    new_version = f'APP_VERSION = "{TARGET_VERSION}"'
    if text.count(old_version) != 1:
        raise SystemExit(f"Version anchor expected one match, found {text.count(old_version)}")
    text = text.replace(old_version, new_version, 1)
    text = apply_arena_v2_patch(text)
    text = apply_arena_v2_pilot_patch(text)
    text = apply_daily_v73_patch(text)
    text = apply_arena_perception_core_patch(text)
    text = apply_arena_perception_integration_patch(text)
    text = apply_arena_perception_events_patch(text)

    output.write_text(text, encoding="utf-8", newline="\n")
    temp.unlink(missing_ok=True)
    py_compile.compile(str(output), doraise=True)
    final = output.read_bytes()
    print(
        f"Generated v{TARGET_VERSION}: {len(final)} bytes, "
        f"sha256={hashlib.sha256(final).hexdigest()}"
    )


if __name__ == "__main__":
    main()
