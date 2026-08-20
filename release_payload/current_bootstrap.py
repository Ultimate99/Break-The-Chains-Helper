# TG:BTC Game Assistant v7.0.7 Daily Debug & Calibration updater
import base64, gzip, hashlib, os, re, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.7"
_EXPECTED_SHA256 = "669044e2d9a99d808c445ab76e2fc4bc7cbe25f5dddb1dc6030bbf12b117dffb"
_PATCH = """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"""

def apply_patch(source, patch_text):
    src = source.splitlines(True)
    out = []
    pos = 0
    lines = patch_text.splitlines(True)
    i = 0
    while i < len(lines) and not lines[i].startswith("@@"):
        i += 1
    while i < len(lines):
        header = lines[i].rstrip("\n")
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
        if not m:
            raise RuntimeError("Invalid v7.0.7 patch hunk")
        old_start = int(m.group(1)) - 1
        if old_start < pos:
            raise RuntimeError("Overlapping v7.0.7 patch hunk")
        out.extend(src[pos:old_start])
        pos = old_start
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line.startswith(" "):
                expected = line[1:]
                if pos >= len(src) or src[pos] != expected:
                    raise RuntimeError(f"v7.0.7 context mismatch near source line {pos+1}")
                out.append(src[pos]); pos += 1
            elif line.startswith("-"):
                expected = line[1:]
                if pos >= len(src) or src[pos] != expected:
                    raise RuntimeError(f"v7.0.7 deletion mismatch near source line {pos+1}")
                pos += 1
            elif line.startswith("+"):
                out.append(line[1:])
            elif line.startswith("\\"):
                pass
            i += 1
    out.extend(src[pos:])
    return "".join(out)

def find_base():
    root = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates = []
    if root.exists():
        candidates += list(root.glob("before_7.0.6_*/tg_arena_bot.py"))
        candidates += [p for p in root.glob("**/tg_arena_bot.py") if p not in candidates]
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s = p.read_text(encoding="utf-8")
            if 'APP_VERSION = "7.0.6"' in s and "def _daily_safe_scan" in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate backed-up v7.0.6 source. Use the v7.0.7 standalone package.")

def main():
    target = Path(__file__).resolve()
    source = find_base()
    patch = gzip.decompress(base64.b64decode(_PATCH)).decode("utf-8")
    result = apply_patch(source, patch)
    actual = hashlib.sha256(result.encode("utf-8")).hexdigest()
    if actual != _EXPECTED_SHA256:
        raise RuntimeError(f"v7.0.7 patched source checksum mismatch: {actual}")
    tmp = target.with_suffix(target.suffix + ".v707.tmp")
    tmp.write_text(result, encoding="utf-8")
    os.replace(tmp, target)
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent), creationflags=flags)

if __name__ == "__main__":
    main()
