# TG:BTC Game Assistant v7.0.4 Daily Home OCR hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.4"
OLD_VERSION = 'APP_VERSION = "7.0.3"'
NEW_VERSION = 'APP_VERSION = "7.0.4"'
OLD_WORKER = '    def _daily_module_worker(self,module):\n        self.daily_active_module=module\n        self._daily_var(module).set("RUNNING")\n        try:\n            if not HAS_TESSERACT:\n                raise RuntimeError("OCR is required for safe Daily collection. Install OCR from Settings.")\n            if get_device() is None:\n                raise RuntimeError("No ADB device connected.")\n            if module!="Current Screen":\n                if not self._daily_ensure_home():\n                    raise RuntimeError("Not on HOME. Open the game Home screen manually, then press START again. Daily Assistant will never press Android Back automatically.")\n                route=(get_daily_settings().get("routes") or {}).get(module) or []\n                if not route:\n                    raise RuntimeError(f"{module} has no route yet. Click TEACH once.")\n                for x,y in route:\n                    if self.daily_stop_event.is_set(): break\n                    self.engine._tap_reference(float(x),float(y)); self.add_log(f"Daily {module}: navigation tap {x},{y}"); time.sleep(1.05)\n            taps=self._daily_safe_scan(module)\n            if self.daily_stop_event.is_set():\n                self._daily_var(module).set("STOPPED")\n            else:\n                self._daily_var(module).set(f"DONE • {taps} TAP" + ("S" if taps!=1 else ""))\n                self.add_log(f"Daily {module}: finished safely • {taps} automated tap(s)")\n        except Exception as e:\n            self._daily_var(module).set("ERROR")\n            self.add_log(f"Daily {module} error: {e}")\n            try: self.root.after(0,lambda: messagebox.showerror("Daily Assistant",str(e)))\n            except Exception: pass\n        finally:\n            self.daily_active_module=None\n'
NEW_WORKER = '    def _daily_module_worker(self,module):\n        self.daily_active_module=module\n        self._daily_var(module).set("RUNNING")\n        try:\n            if not HAS_TESSERACT:\n                self._daily_var(module).set("OCR MISSING")\n                raise RuntimeError("OCR is required for safe Daily collection. Install OCR from Settings.")\n            dev = get_device()\n            if dev is None:\n                self._daily_var(module).set("NO ADB")\n                raise RuntimeError("No ADB device connected.")\n            # Daily modules use the user\'s explicit contract: START them from HOME.\n            # Do not OCR-gate Home — TG:BTC\'s stylized home labels are not reliably\n            # readable by Tesseract and caused false ERROR states in v7.0-v7.0.3.\n            # Also never press Android Back automatically.\n            if not self.engine.device:\n                self.engine.device = dev\n            if module!="Current Screen":\n                route=(get_daily_settings().get("routes") or {}).get(module) or []\n                if not route:\n                    self._daily_var(module).set("NEEDS ROUTE")\n                    raise RuntimeError(f"{module} has no route yet. Click TEACH once.")\n                self.add_log(f"Daily {module}: HOME assumed by user START contract")\n                for x,y in route:\n                    if self.daily_stop_event.is_set(): break\n                    self.engine._tap_reference(float(x),float(y)); self.add_log(f"Daily {module}: navigation tap {x},{y}"); time.sleep(1.05)\n            taps=self._daily_safe_scan(module)\n            if self.daily_stop_event.is_set():\n                self._daily_var(module).set("STOPPED")\n            else:\n                self._daily_var(module).set(f"DONE • {taps} TAP" + ("S" if taps!=1 else ""))\n                self.add_log(f"Daily {module}: finished safely • {taps} automated tap(s)")\n        except Exception as e:\n            msg = str(e)\n            current = self._daily_var(module).get()\n            if current in ("RUNNING", "READY", "ERROR"):\n                short = msg.upper()\n                if len(short) > 26:\n                    short = short[:23] + "..."\n                self._daily_var(module).set(short)\n            self.add_log(f"Daily {module} error: {msg}")\n            try: self.root.after(0,lambda m=msg: messagebox.showerror("Daily Assistant",m))\n            except Exception: pass\n        finally:\n            self.daily_active_module=None\n'

def find_base():
    appdata = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates=[]
    if appdata.exists():
        for p in appdata.glob("before_7.0.3_*/tg_arena_bot.py"):
            candidates.append(p)
        for p in appdata.glob("**/tg_arena_bot.py"):
            if p not in candidates:
                candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for p in candidates:
        try:
            s=p.read_text(encoding="utf-8")
            if OLD_VERSION in s and OLD_WORKER in s:
                return s
        except Exception:
            pass
    raise RuntimeError("Could not locate the backed-up v7.0.3 source. Use the 7.0.4 standalone package instead.")

def main():
    target=Path(__file__).resolve()
    s=find_base()
    s=s.replace(OLD_VERSION,NEW_VERSION,1)
    s=s.replace(OLD_WORKER,NEW_WORKER,1)
    tmp=target.with_suffix(target.suffix+".v704.tmp")
    tmp.write_text(s,encoding="utf-8")
    os.replace(tmp,target)
    flags=0x08000000 if os.name=="nt" else 0
    subprocess.Popen([sys.executable,str(target)],cwd=str(target.parent),creationflags=flags)

if __name__=="__main__":
    main()
