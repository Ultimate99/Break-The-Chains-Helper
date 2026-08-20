# TG:BTC Arena Companion v5.7 delta bootstrap
# Applies the v5.6 -> v5.7 History + Opponent Intelligence update from the updater backup.
import base64
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_VERSION = "5.7.0"
_BASE_SHA256 = "4204a28872d18d5b367a04700ca2ee006d49d7631b0fa64332c47fa99848781c"
_TARGET_SHA256 = "db111018cc05ebb9bd59638cdcf338c357c9bb04021e7fb23941ba9a14a91712"
_DELTA = """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"""

def _sha(data):
    return hashlib.sha256(data).hexdigest()

def _profile_dir():
    root = Path(os.environ.get("APPDATA", str(Path(__file__).resolve().parent)))
    return root / "TG-BTC-Arena-Companion"

def _find_base_backup():
    backup_root = _profile_dir() / "update_backups"
    if not backup_root.exists():
        raise RuntimeError("v5.7 could not find the updater backup folder")
    candidates = sorted(
        [p for p in backup_root.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for folder in candidates:
        src = folder / "tg_arena_bot.py"
        if not src.exists():
            continue
        data = src.read_bytes()
        if _sha(data) == _BASE_SHA256:
            return src, data
    raise RuntimeError("v5.7 needs the v5.6 source backup but an exact match was not found")

def _apply_delta(base_text):
    lines = base_text.splitlines(keepends=True)
    ops = json.loads(gzip.decompress(base64.b64decode(_DELTA)).decode("utf-8"))
    out = []
    cursor = 0
    for tag, i1, i2, replacement in ops:
        out.extend(lines[cursor:i1])
        if tag in ("replace", "insert") and replacement:
            out.append(replacement)
        cursor = i2
    out.extend(lines[cursor:])
    return "".join(out)

def _relaunch(target):
    kwargs = {"cwd": str(target.parent)}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen([sys.executable, str(target)], **kwargs)

def main():
    target = Path(__file__).resolve()
    backup_path = None
    try:
        backup_path, base_bytes = _find_base_backup()
        patched = _apply_delta(base_bytes.decode("utf-8"))
        patched_bytes = patched.encode("utf-8")
        if _sha(patched_bytes) != _TARGET_SHA256:
            raise RuntimeError("v5.7 delta verification failed")
        tmp = target.with_suffix(".v57.tmp")
        tmp.write_bytes(patched_bytes)
        os.replace(tmp, target)
        _relaunch(target)
    except Exception as exc:
        # Restore the exact pre-update app if anything unexpected happens.
        try:
            if backup_path and backup_path.exists():
                shutil.copy2(backup_path, target)
                _relaunch(target)
        finally:
            try:
                log = _profile_dir() / "updater.log"
                with log.open("a", encoding="utf-8") as f:
                    f.write(f"v5.7 delta bootstrap failed: {exc}\n")
            except Exception:
                pass

if __name__ == "__main__":
    main()
