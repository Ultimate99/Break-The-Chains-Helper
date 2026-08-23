#!/usr/bin/env python3
"""Entry point for deterministic TG:BTC full-source release builds.

The implementation is stored compressed beside this file to keep the release
payload compact. It reconstructs the checksum-verified v7.1.2 full source and
applies the v7.2 Vision-First patch when VERSION is 7.2.0.
"""
import base64
import gzip
from pathlib import Path

payload = Path(__file__).with_name("build_release_v720.py.gz.b64").read_text(encoding="utf-8").strip()
source = gzip.decompress(base64.b64decode(payload)).decode("utf-8")
exec(compile(source, "build_release_v720.py", "exec"), globals(), globals())
