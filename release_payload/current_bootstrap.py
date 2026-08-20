# TG:BTC Game Assistant v7.0.5 stability hotfix bootstrap
import os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.0.5"

def main():
    target = Path(__file__).resolve()
    profile = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates = []
    if profile.exists():
        candidates += list(profile.glob("before_7.0.4_*/tg_arena_bot.py"))
        candidates += [p for p in profile.glob("**/tg_arena_bot.py") if p not in candidates]
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    source = None
    for p in candidates:
        try:
            s = p.read_text(encoding="utf-8")
            if 'APP_VERSION = "7.0.4"' in s and 'def _daily_module_worker' in s:
                source = s
                break
        except Exception:
            pass
    if source is None:
        raise RuntimeError("Could not locate the backed-up v7.0.4 source. Use the 7.0.5 standalone package instead.")
    old = 'APP_VERSION = "7.0.4"'
    new = 'APP_VERSION = "7.0.5"'
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    old = '    def open_daily_assistant(self):\n'
    new = "    def _daily_set_status(self, module, text):\n        # Tk variables must only be touched from Tk's UI thread. Daily workers\n        # run in background threads, so marshal status updates through after().\n        def apply():\n            try:\n                self._daily_var(module).set(text)\n            except Exception:\n                pass\n        try:\n            self.root.after(0, apply)\n        except Exception:\n            pass\n\n    def open_daily_assistant(self):\n"
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    old = '        self.daily_module_vars = {}\n'
    new = '        # Preserve module StringVars when reopening the page so a running\n        # worker never loses the variables its cards are bound to.\n        if not hasattr(self, "daily_module_vars") or self.daily_module_vars is None:\n            self.daily_module_vars = {}\n'
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    old = '                try:\n                    self.engine._tap_reference(x,y)\n                    time.sleep(1.0)\n                except Exception: pass\n                self.root.after(50,pick_next)\n'
    new = "                try:\n                    self.engine._tap_reference(x,y)\n                except Exception:\n                    pass\n                # Do not block Tk's UI thread while waiting for the next screen.\n                self.root.after(1000, pick_next)\n"
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    old = '        while taps<max_taps and empty<3 and not self.daily_stop_event.is_set():\n'
    new = '        # Give slower menus/load transitions a few seconds before declaring that\n        # there are no safe actions. Three OCR misses was too aggressive.\n        while taps<max_taps and empty<7 and not self.daily_stop_event.is_set():\n'
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    old = '    def _daily_module_worker(self,module):\n        self.daily_active_module=module\n        self._daily_var(module).set("RUNNING")\n        try:\n            if not HAS_TESSERACT:\n                self._daily_var(module).set("OCR MISSING")\n                raise RuntimeError("OCR is required for safe Daily collection. Install OCR from Settings.")\n            dev = get_device()\n            if dev is None:\n                self._daily_var(module).set("NO ADB")\n                raise RuntimeError("No ADB device connected.")\n            # Daily modules use the user\'s explicit contract: START them from HOME.\n            # Do not OCR-gate Home — TG:BTC\'s stylized home labels are not reliably\n            # readable by Tesseract and caused false ERROR states in v7.0-v7.0.3.\n            # Also never press Android Back automatically.\n            if not self.engine.device:\n                self.engine.device = dev\n            if module!="Current Screen":\n                route=(get_daily_settings().get("routes") or {}).get(module) or []\n                if not route:\n                    self._daily_var(module).set("NEEDS ROUTE")\n                    raise RuntimeError(f"{module} has no route yet. Click TEACH once.")\n                self.add_log(f"Daily {module}: HOME assumed by user START contract")\n                for x,y in route:\n                    if self.daily_stop_event.is_set(): break\n                    self.engine._tap_reference(float(x),float(y)); self.add_log(f"Daily {module}: navigation tap {x},{y}"); time.sleep(1.05)\n            taps=self._daily_safe_scan(module)\n            if self.daily_stop_event.is_set():\n                self._daily_var(module).set("STOPPED")\n            else:\n                self._daily_var(module).set(f"DONE • {taps} TAP" + ("S" if taps!=1 else ""))\n                self.add_log(f"Daily {module}: finished safely • {taps} automated tap(s)")\n        except Exception as e:\n            msg = str(e)\n            current = self._daily_var(module).get()\n            if current in ("RUNNING", "READY", "ERROR"):\n                short = msg.upper()\n                if len(short) > 26:\n                    short = short[:23] + "..."\n                self._daily_var(module).set(short)\n            self.add_log(f"Daily {module} error: {msg}")\n            try: self.root.after(0,lambda m=msg: messagebox.showerror("Daily Assistant",m))\n            except Exception: pass\n        finally:\n            self.daily_active_module=None\n\n'
    new = '    def _daily_module_worker(self,module):\n        self.daily_active_module=module\n        self._daily_set_status(module, "RUNNING")\n        try:\n            if not HAS_TESSERACT:\n                self._daily_set_status(module, "OCR MISSING")\n                raise RuntimeError("OCR is required for safe Daily collection. Install OCR from Settings.")\n            dev = get_device()\n            if dev is None:\n                self._daily_set_status(module, "NO ADB")\n                raise RuntimeError("No ADB device connected.")\n            # Always refresh the engine serial. Wireless ADB can reconnect with a\n            # different active device/session after sleep or network changes.\n            self.engine.device = dev\n            if module!="Current Screen":\n                route=(get_daily_settings().get("routes") or {}).get(module) or []\n                if not route:\n                    self._daily_set_status(module, "NEEDS ROUTE")\n                    raise RuntimeError(f"{module} has no route yet. Click TEACH once.")\n                self.add_log(f"Daily {module}: HOME assumed by user START contract")\n                for x,y in route:\n                    if self.daily_stop_event.is_set():\n                        break\n                    self.engine._tap_reference(float(x),float(y))\n                    self.add_log(f"Daily {module}: navigation tap {x},{y}")\n                    time.sleep(1.20)\n                # Final route tap may open a heavier page; let it settle before OCR.\n                if not self.daily_stop_event.is_set():\n                    time.sleep(0.65)\n            taps=self._daily_safe_scan(module)\n            if self.daily_stop_event.is_set():\n                self._daily_set_status(module, "STOPPED")\n            else:\n                self._daily_set_status(module, f"DONE • {taps} TAP" + ("S" if taps!=1 else ""))\n                self.add_log(f"Daily {module}: finished safely • {taps} automated tap(s)")\n        except Exception as e:\n            msg = str(e)\n            if "no route" not in msg.lower() and "OCR is required" not in msg and "No ADB" not in msg:\n                short = msg.upper()\n                if len(short) > 26:\n                    short = short[:23] + "..."\n                self._daily_set_status(module, short)\n            self.add_log(f"Daily {module} error: {msg}")\n            try:\n                self.root.after(0, lambda m=msg: messagebox.showerror("Daily Assistant", m))\n            except Exception:\n                pass\n        finally:\n            self.daily_active_module=None\n\n'
    if old not in source:
        raise RuntimeError("v7.0.5 patch marker missing")
    source = source.replace(old, new, 1)
    tmp = target.with_suffix(target.suffix + ".v705.tmp")
    tmp.write_text(source, encoding="utf-8")
    os.replace(tmp, target)
    flags = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent), creationflags=flags)

if __name__ == "__main__":
    main()
