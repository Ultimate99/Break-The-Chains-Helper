#!/usr/bin/env python3
"""Checksum-verified V7.3 Arena Pilot build-time patch."""
import base64
import gzip
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "8ddbc98bf9b4eb3fa465dac0d725965c902c49dcb51a54b4898c40efc8af7fb5"
root = Path(__file__).resolve().parent
parts_dir = root / "arena_v2_pilot_patch_parts"
parts = sorted(parts_dir.glob("part*.txt"))
if not parts:
    raise RuntimeError("Arena Pilot patch parts are missing")
payload = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
source = gzip.decompress(base64.b64decode(payload))
got = hashlib.sha256(source).hexdigest()
if got != EXPECTED_SHA256:
    raise RuntimeError(f"Arena Pilot patch checksum mismatch: {got}")
namespace = {}
exec(compile(source.decode("utf-8"), "arena_v2_pilot_patch_impl.py", "exec"), namespace, namespace)
apply_arena_v2_pilot_patch = namespace["apply_arena_v2_pilot_patch"]
