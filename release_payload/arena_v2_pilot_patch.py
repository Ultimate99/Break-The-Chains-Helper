#!/usr/bin/env python3
"""Checksum-verified V7.3 Arena Pilot build-time patch."""
import base64
import gzip
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "e9616e9d78495bc63d29775dcc83dcf91c4e5c9e50d80adfc105be52640e275f"
root = Path(__file__).resolve().parent
payload = (root / "arena_v2_pilot_patch_payload.txt").read_text(encoding="utf-8").strip()
source = gzip.decompress(base64.b64decode(payload))
got = hashlib.sha256(source).hexdigest()
if got != EXPECTED_SHA256:
    raise RuntimeError(f"Arena Pilot patch checksum mismatch: {got}")
namespace = {}
exec(compile(source.decode("utf-8"), "arena_v2_pilot_patch_impl.py", "exec"), namespace, namespace)
apply_arena_v2_pilot_patch = namespace["apply_arena_v2_pilot_patch"]
