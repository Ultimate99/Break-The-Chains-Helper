# TG:BTC Arena Companion v5.7.1 delta bootstrap
# Reconstructs v5.7.1 from the updater backup of v5.7.0, then restarts.
import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

APP_VERSION = "5.7.1"
_BASE_SHA256 = "db111018cc05ebb9bd59638cdcf338c357c9bb04021e7fb23941ba9a14a91712"
_TARGET_SHA256 = "0941b187368de010103ec0e03b67821e9b204cb0416dc5a28d9941060c2a0daf"
_DELTA = """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"""

def find_base(profile_dir):
    backup_root = profile_dir / "update_backups"
    candidates = []
    if backup_root.exists():
        for folder in backup_root.glob("before_5.7.0_*"):
            main = folder / "tg_arena_bot.py"
            if main.exists():
                candidates.append(main)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for main in candidates:
        raw = main.read_bytes()
        if hashlib.sha256(raw).hexdigest() == _BASE_SHA256:
            return main
    raise RuntimeError("Could not find the v5.7.0 updater backup required for the 5.7.1 delta")

def apply_delta(base_text):
    lines = base_text.splitlines(keepends=True)
    ops = json.loads(gzip.decompress(base64.b64decode(_DELTA)).decode("utf-8"))
    out = []
    for op in ops:
        tag = op[0]
        i1, i2 = int(op[1]), int(op[2])
        if tag == "=":
            out.extend(lines[i1:i2])
        else:
            out.append(op[3])
    return "".join(out)

def main():
    target = Path(__file__).resolve()
    appdata = Path(os.environ.get("APPDATA", str(target.parent)))
    profile_dir = appdata / "TG-BTC-Arena-Companion"
    base_file = find_base(profile_dir)
    rebuilt = apply_delta(base_file.read_text(encoding="utf-8"))
    raw = rebuilt.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != _TARGET_SHA256:
        raise RuntimeError("v5.7.1 reconstructed source checksum mismatch")
    tmp = target.with_suffix(".v571.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)
    kwargs = {"cwd": str(target.parent)}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen([sys.executable, str(target)], **kwargs)

if __name__ == "__main__":
    main()
