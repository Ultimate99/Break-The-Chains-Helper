# TG:BTC Game Assistant v7.0.6 Daily tap-scaling hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.6"
OLD_VERSION = 'APP_VERSION = "7.0.5"'
NEW_VERSION = 'APP_VERSION = "7.0.6"'

OLD_PHONE = '    def _phone_reference_screenshot(self):\n        screen = capture_screen()\n        return resize_reference(screen)\n'
NEW_PHONE = '    def _phone_reference_screenshot(self):\n        # Daily Assistant can run while the Arena engine itself is stopped.\n        # Keep real phone geometry synced so reference-space taps are scaled.\n        screen = capture_screen()\n        try:\n            actual_h, actual_w = screen.shape[:2]\n            self.engine.actual_w = int(actual_w)\n            self.engine.actual_h = int(actual_h)\n        except Exception:\n            pass\n        return resize_reference(screen)\n'

OLD_EMPTY = '        while taps<max_taps and empty<7 and not self.daily_stop_event.is_set():\n'
NEW_EMPTY = '        while taps<max_taps and empty<2 and not self.daily_stop_event.is_set():\n'

OLD_DEVICE = '            # Always refresh the engine serial. Wireless ADB can reconnect with a\n            # different active device/session after sleep or network changes.\n            self.engine.device = dev\n            if module!="Current Screen":\n'
NEW_DEVICE = '            # Always refresh the engine serial. Wireless ADB can reconnect with a\n            # different active device/session after sleep or network changes.\n            self.engine.device = dev\n\n            # V7.0.6: synchronize physical phone geometry BEFORE the first route\n            # tap. Daily runs with the Arena engine stopped, so actual_w/actual_h\n            # would otherwise still be the 1536x709 reference defaults.\n            self._daily_set_status(module, "SYNCING")\n            self._phone_reference_screenshot()\n            self.add_log(f"Daily {module}: device geometry {self.engine.actual_w}x{self.engine.actual_h}")\n            self._daily_set_status(module, "RUNNING")\n\n            if module!="Current Screen":\n'

def find_base():
    root = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates=[]
    if root.exists():
        candidates += list(root.glob("before_7.0.5_*/tg_arena_bot.py"))
        candidates += [p for p in root.glob("**/tg_arena_bot.py") if p not in candidates]
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s=p.read_text(encoding="utf-8")
            if OLD_VERSION in s and OLD_PHONE in s and OLD_DEVICE in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate the backed-up v7.0.5 source. Use the 7.0.6 standalone package instead.")

def main():
    target=Path(__file__).resolve()
    s=find_base()
    if OLD_EMPTY not in s:
        raise RuntimeError("v7.0.6 scan marker missing")
    s=s.replace(OLD_VERSION,NEW_VERSION,1)
    s=s.replace(OLD_PHONE,NEW_PHONE,1)
    s=s.replace(OLD_EMPTY,NEW_EMPTY,1)
    s=s.replace(OLD_DEVICE,NEW_DEVICE,1)
    tmp=target.with_suffix(target.suffix+".v706.tmp")
    tmp.write_text(s,encoding="utf-8")
    os.replace(tmp,target)
    flags=0x08000000 if os.name=="nt" else 0
    subprocess.Popen([sys.executable,str(target)],cwd=str(target.parent),creationflags=flags)

if __name__=="__main__":
    main()
