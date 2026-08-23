#!/usr/bin/env python3
"""Deterministic TG:BTC full-source release build entry point."""
import base64
import bz2
import gzip
import hashlib
import json
import os
import subprocess
import sys
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

try:
    exec(compile(source, "build_release_v720.py", "exec"), globals(), globals())
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise


def _cli_arg(flag):
    try:
        i = sys.argv.index(flag)
        return sys.argv[i + 1]
    except (ValueError, IndexError):
        return None


def _write_current_source_manifest():
    version = str(_cli_arg("--version") or "").strip().lstrip("vV")
    output = _cli_arg("--output")
    if not version or not output:
        return
    source_path = Path(output)
    if not source_path.exists():
        return

    raw = source_path.read_bytes()
    text = raw.decode("utf-8")
    if f'APP_VERSION = "{version}"' not in text and f"APP_VERSION = '{version}'" not in text:
        raise SystemExit("Refusing to publish updater manifest: source APP_VERSION mismatch")

    encoded = base64.b64encode(bz2.compress(raw, compresslevel=9)).decode("ascii")
    out_dir = root / "current_source_parts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("part*.txt"):
        stale.unlink()

    chunk_size = 20000
    rel_parts = []
    for idx in range(0, len(encoded), chunk_size):
        name = f"part{idx // chunk_size + 1:02d}.txt"
        (out_dir / name).write_text(encoded[idx:idx + chunk_size], encoding="utf-8")
        rel_parts.append(f"current_source_parts/{name}")

    manifest = {
        "version": version,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "encoding": "base64+bz2",
        "parts": rel_parts,
    }
    manifest_path = root / "current_source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Updater manifest ready: v{version}, {len(raw)} bytes, "
        f"sha256={manifest['sha256']}, parts={len(rel_parts)}"
    )

    # Persist the fallback during real GitHub release builds. The release
    # workflow only triggers on VERSION/workflow changes, so this bot commit
    # does not recursively start another release run.
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run([
            "git", "config", "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ], check=True)
        subprocess.run([
            "git", "add", "-A",
            "release_payload/current_source_manifest.json",
            "release_payload/current_source_parts",
        ], check=True)
        changed = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
        if changed:
            subprocess.run([
                "git", "commit", "-m",
                f"Publish updater source manifest v{version} [skip ci]",
            ], check=True)
            subprocess.run(["git", "push"], check=True)


_write_current_source_manifest()
