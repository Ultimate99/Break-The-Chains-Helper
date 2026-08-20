# TG:BTC Game Assistant v7.0.3 Windows Minimize hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.3"
OLD_VERSION = 'APP_VERSION = "7.0.2"'
NEW_VERSION = 'APP_VERSION = "7.0.3"'

OLD = '''    def _minimize_window(self):\n        if os.name == "nt":\n            try:\n                import ctypes\n                hwnd = self._native_hwnd()\n                if hwnd:\n                    ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE\n                    return\n            except Exception:\n                pass\n\n        # Portable fallback.  Restore custom chrome after deiconify/map.\n        try:\n            self.root.overrideredirect(False)\n            self.root.iconify()\n        except Exception:\n            pass\n\n    def _on_window_map(self, event=None):\n        # Needed by the non-Windows minimize fallback.\n        try:\n            if self.root.state() == "normal":\n                self.root.overrideredirect(True)\n                self.root.after(25, self._ensure_taskbar_presence)\n        except Exception:\n            pass\n'''

NEW = '''    def _minimize_window(self):\n        # V7.0.3: never call ShowWindow() on a guessed Tk parent HWND.\n        # Temporarily restore native window management, iconify through Tk,\n        # then re-apply custom dark chrome when the window is restored.\n        try:\n            self._minimize_pending = True\n            self.root.overrideredirect(False)\n            self.root.update_idletasks()\n            self.root.iconify()\n        except Exception:\n            self._minimize_pending = False\n\n    def _on_window_map(self, event=None):\n        try:\n            if self.root.state() == "normal":\n                self.root.overrideredirect(True)\n                self._minimize_pending = False\n                self.root.after(25, self._ensure_taskbar_presence)\n        except Exception:\n            pass\n'''

def find_base():
    root = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates=[]
    if root.exists():
        candidates += list(root.glob("before_7.0.2_*/tg_arena_bot.py"))
        candidates += [p for p in root.glob("**/tg_arena_bot.py") if p not in candidates]
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s=p.read_text(encoding="utf-8")
            if OLD_VERSION in s and OLD in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate the backed-up v7.0.2 source. Use the 7.0.3 standalone package instead.")

def main():
    target=Path(__file__).resolve()
    s=find_base()
    s=s.replace(OLD_VERSION,NEW_VERSION,1).replace(OLD,NEW,1)
    tmp=target.with_suffix(target.suffix+".v703.tmp")
    tmp.write_text(s,encoding="utf-8")
    os.replace(tmp,target)
    flags=0x08000000 if os.name=="nt" else 0
    subprocess.Popen([sys.executable,str(target)],cwd=str(target.parent),creationflags=flags)

if __name__ == "__main__":
    main()
