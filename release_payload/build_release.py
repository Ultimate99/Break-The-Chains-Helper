#!/usr/bin/env python3
"""Deterministic TG:BTC full-source release build entry point."""
import base64
import gzip
import hashlib
from pathlib import Path

EXPECTED_BUILDER_SHA256 = "bf120e8e651ce0139cefa36e99d3f76f880b11941b863480708be6fb30107a8e"
EXPECTED_PATCHED_SHA256 = "78f8ba945800eb390f9778a01b8d6ea38484a2d47b887b9544407f61465eafb7"
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

# Build-tool hotfix: distinguish the App.__init__ Daily transport state from
# the identical shutdown-state assignment elsewhere in v7.1.2.
old1 = '''    init_old = \'\'\'        self.daily_vision = None\\n        self.daily_tap_shell = None\\n        self.daily_transport_device = None\\n\'\'\'\n    init_new = init_old + \'\'\'        # V7.2 Vision Inspector / shared visual understanding state.\\n'''
new1 = '''    init_old = \'\'\'        self.daily_vision = None\\n        self.daily_tap_shell = None\\n        self.daily_transport_device = None\\n        self.health_overall_var = tk.StringVar(value="SYSTEM IDLE")\\n\'\'\'\n    init_new = init_old.replace(\'        self.health_overall_var = tk.StringVar(value="SYSTEM IDLE")\\n\', \'\') + \'\'\'        # V7.2 Vision Inspector / shared visual understanding state.\\n'''
old2 = '''        self.vision_last_result = None\\n        self.vision_analysis_cache = None\\n\'\'\'\n    text = replace_once(text, init_old, init_new, "vision init")'''
new2 = '''        self.vision_last_result = None\\n        self.vision_analysis_cache = None\\n        self.health_overall_var = tk.StringVar(value="SYSTEM IDLE")\\n\'\'\'\n    text = replace_once(text, init_old, init_new, "vision init")'''
for old, new, label in ((old1, new1, "vision-init anchor"), (old2, new2, "vision-init tail")):
    if source.count(old) != 1:
        raise SystemExit(f"Release-builder hotfix {label} expected one match, found {source.count(old)}")
    source = source.replace(old, new, 1)
patched_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
if patched_sha != EXPECTED_PATCHED_SHA256:
    raise SystemExit(f"Patched release-builder checksum mismatch: {patched_sha}")
exec(compile(source, "build_release_v720.py", "exec"), globals(), globals())
