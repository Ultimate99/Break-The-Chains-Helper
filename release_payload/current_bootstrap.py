# TG:BTC Game Assistant v7.0.2 Daily Home Guard hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.2"
OLD_VERSION = 'APP_VERSION = "7.0.1"'
NEW_VERSION = 'APP_VERSION = "7.0.2"'

OLD_HOME = '''    def _daily_ensure_home(self):\n        # Conservative: only use Android Back while OCR positively tells us we\n        # are not yet on Home. Give up rather than guessing.\n        for _ in range(5):\n            if self.daily_stop_event.is_set(): return False\n            ref=self._phone_reference_screenshot()\n            if self._daily_home_signature(ref): return True\n            adb(["shell","input","keyevent","4"])\n            time.sleep(0.75)\n        return self._daily_home_signature(self._phone_reference_screenshot())\n'''

NEW_HOME = '''    def _daily_ensure_home(self):\n        # V7.0.2 safety rule: Daily modules NEVER send Android Back to find Home.\n        # In TG:BTC, Back from Home opens/exits the game, so navigation-to-Home\n        # must be user-controlled. We only verify the current screen here.\n        if self.daily_stop_event.is_set():\n            return False\n        try:\n            ref = self._phone_reference_screenshot()\n            return self._daily_home_signature(ref)\n        except Exception:\n            return False\n'''

OLD_ERROR = 'raise RuntimeError("Could not verify HOME screen. Open Home manually and retry.")'
NEW_ERROR = 'raise RuntimeError("Not on HOME. Open the game Home screen manually, then press START again. Daily Assistant will never press Android Back automatically.")'

def find_base():
    appdata = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates = []
    if appdata.exists():
        for p in appdata.glob("before_7.0.1_*/tg_arena_bot.py"):
            candidates.append(p)
        for p in appdata.glob("**/tg_arena_bot.py"):
            if p not in candidates:
                candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s = p.read_text(encoding="utf-8")
            if OLD_VERSION in s and OLD_HOME in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate the backed-up v7.0.1 source. Use the 7.0.2 standalone package instead.")

def main():
    target = Path(__file__).resolve()
    s = find_base()
    if OLD_HOME not in s:
        raise RuntimeError("v7.0.2 Home Guard patch marker not found")
    s = s.replace(OLD_VERSION, NEW_VERSION, 1)
    s = s.replace(OLD_HOME, NEW_HOME, 1)
    s = s.replace(OLD_ERROR, NEW_ERROR, 1)
    tmp = target.with_suffix(target.suffix + ".v702.tmp")
    tmp.write_text(s, encoding="utf-8")
    os.replace(tmp, target)
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent), creationflags=flags)

if __name__ == "__main__":
    main()
