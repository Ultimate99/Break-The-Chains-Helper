#!/usr/bin/env python3
"""Checksum-verified loader for the Arena V2 build-time source patch."""
import base64
import gzip
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "80ccad8fe9483592e9ca7f864e18046c1066bb8aaba85c6f2e1b733be8710d30"
root = Path(__file__).resolve().parent
payload = (root / "arena_v2_patch_payload.txt").read_text(encoding="utf-8").strip()
source = gzip.decompress(base64.b64decode(payload))
got = hashlib.sha256(source).hexdigest()
if got != EXPECTED_SHA256:
    raise RuntimeError(f"Arena V2 patch checksum mismatch: {got}")
namespace = {}
exec(compile(source.decode("utf-8"), "arena_v2_patch_impl.py", "exec"), namespace, namespace)
apply_arena_v2_patch = namespace["apply_arena_v2_patch"]
