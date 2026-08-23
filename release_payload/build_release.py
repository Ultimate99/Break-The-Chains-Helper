#!/usr/bin/env python3
"""Deterministic TG:BTC full-source release build entry point."""
import base64
import gzip
import hashlib
from pathlib import Path

EXPECTED_BUILDER_SHA256 = "bf120e8e651ce0139cefa36e99d3f76f880b11941b863480708be6fb30107a8e"
root = Path(__file__).resolve().parent
parts_dir = root / "build_release_v720_parts"
parts = sorted(parts_dir.glob("part*.txt"))
if not parts:
    raise SystemExit("Missing v7.2 release-builder chunks")
payload = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
source_bytes = gzip.decompress(base64.b64decode(payload))
got = hashlib.sha256(source_bytes).hexdigest()
if got != EXPECTED_BUILDER_SHA256:
    raise SystemExit(f"Release-builder checksum mismatch: {got}")
source = source_bytes.decode("utf-8")
exec(compile(source, "build_release_v720.py", "exec"), globals(), globals())
