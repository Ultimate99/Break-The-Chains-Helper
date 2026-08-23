#!/usr/bin/env python3
'''Deterministic TG:BTC full-source release build entry point.'''
import base64
import bz2
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXPECTED_BUILDER_SHA256 = "bf120e8e651ce0139cefa36e99d3f76f880b11941b863480708be6fb30107a8e"
EXPECTED_PATCHED_SHA256 = "78f8ba945800eb390f9778a01b8d6ea38484a2d47b887b9544407f61465eafb7"
V720_SOURCE_SHA256 = "8ea07afd9ba27e9040947fab82ee456e122ea48c37d24ca607c0b02747486a7c"
V721_HOME_SOFT_LIMIT = 20.0
V722_ROUTE_SETTLE_TIMEOUT = 2.40

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


def _cli_arg(flag, argv=None):
    args = sys.argv if argv is None else argv
    try:
        i = args.index(flag)
        return args[i + 1]
    except (ValueError, IndexError):
        return None


def _set_cli_arg(args, flag, value):
    out = list(args)
    try:
        i = out.index(flag)
    except ValueError:
        out.extend([flag, value])
    else:
        if i + 1 >= len(out):
            out.append(value)
        else:
            out[i + 1] = value
    return out


def _apply_v721_home_hotfix(text):
    anchor_old = '''        if name in accepted:\n            ok = screen in accepted[name]\n            return ok, f"vision={screen} {conf:.0f}% • {detail}"\n        return True, "no anchor configured"\n'''
    anchor_new = f'''        if name in accepted:\n            ok = screen in accepted[name]\n            # V7.2.1: HOME is the only screen allowed a bounded soft match.\n            # Live Home art/animation can shift its pHash farther than the\n            # recorded reference even though HOME remains the nearest screen.\n            if not ok and name == "HOME" and screen == "UNKNOWN":\n                match = re.search(r"nearest\\s+HOME\\s+d=([0-9.]+)", str(detail or ""))\n                if match:\n                    try:\n                        home_distance = float(match.group(1))\n                    except Exception:\n                        home_distance = 999.0\n                    if home_distance <= {V721_HOME_SOFT_LIMIT:.1f}:\n                        return True, (\n                            f"vision=HOME~ {{conf:.0f}}% • soft {{detail}} "\n                            f"(limit={V721_HOME_SOFT_LIMIT:.1f})"\n                        )\n            return ok, f"vision={{screen}} {{conf:.0f}}% • {{detail}}"\n        return True, "no anchor configured"\n'''
    if text.count(anchor_old) != 1:
        raise SystemExit(f"v7.2.1 HOME anchor expected one match, found {text.count(anchor_old)}")
    return text.replace(anchor_old, anchor_new, 1)


def _apply_v722_route_hotfix(text):
    route_old = '''                    if expected:\n                        ok,detail=self._daily_anchor_check(expected,last_after)\n                        if not ok:\n                            ok,detail,last_after=self._daily_wait_anchor(expected,timeout=0.85,initial_ref=last_after)\n'''
    route_new = f'''                    if expected:\n                        ok,detail=self._daily_anchor_check(expected,last_after)\n                        if not ok:\n                            # V7.2.2: the first changed frame is often only a transition.\n                            # Keep polling for the expected destination; return immediately\n                            # when it settles, but allow slower emulator/network frames.\n                            ok,detail,last_after=self._daily_wait_anchor(\n                                expected, timeout={V722_ROUTE_SETTLE_TIMEOUT:.2f}, initial_ref=last_after\n                            )\n'''
    if text.count(route_old) != 1:
        raise SystemExit(f"v7.2.2 route anchor expected one match, found {text.count(route_old)}")
    return text.replace(route_old, route_new, 1)


def _run_base_builder(builder_source):
    requested_argv = list(sys.argv)
    requested_version = str(_cli_arg("--version", requested_argv) or "").strip().lstrip("vV")
    requested_output = _cli_arg("--output", requested_argv)
    is_hotfix = requested_version in {"7.2.1", "7.2.2"}

    temp_output = None
    try:
        if is_hotfix:
            if not requested_output:
                raise SystemExit(f"v{requested_version} build requires --output")
            requested_path = Path(requested_output)
            temp_output = requested_path.with_name(requested_path.name + ".v720base")
            build_argv = _set_cli_arg(requested_argv, "--version", "7.2.0")
            build_argv = _set_cli_arg(build_argv, "--output", str(temp_output))
            sys.argv = build_argv
        try:
            exec(compile(builder_source, "build_release_v720.py", "exec"), globals(), globals())
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
    finally:
        sys.argv = requested_argv

    if not is_hotfix:
        return
    if temp_output is None or not temp_output.exists():
        raise SystemExit(f"v{requested_version} base source was not generated")

    raw = temp_output.read_bytes()
    base_sha = hashlib.sha256(raw).hexdigest()
    if base_sha != V720_SOURCE_SHA256:
        raise SystemExit(f"v{requested_version} base checksum mismatch: {base_sha}")

    text = raw.decode("utf-8")
    version_old = 'APP_VERSION = "7.2.0"'
    version_new = f'APP_VERSION = "{requested_version}"'
    if text.count(version_old) != 1:
        raise SystemExit(f"v{requested_version} version anchor expected one match, found {text.count(version_old)}")
    text = text.replace(version_old, version_new, 1)
    text = _apply_v721_home_hotfix(text)
    if requested_version == "7.2.2":
        text = _apply_v722_route_hotfix(text)

    requested_path = Path(requested_output)
    requested_path.parent.mkdir(parents=True, exist_ok=True)
    requested_path.write_text(text, encoding="utf-8", newline="\n")
    temp_output.unlink(missing_ok=True)
    final_raw = requested_path.read_bytes()
    print(
        f"Generated v{requested_version} hotfix: {len(final_raw)} bytes, "
        f"sha256={hashlib.sha256(final_raw).hexdigest()}"
    )


_run_base_builder(source)


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

    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
        and os.environ.get("TG_SKIP_MANIFEST_PUBLISH") != "1"
    ):
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
