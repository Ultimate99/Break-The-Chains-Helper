#!/usr/bin/env python3
"""V7.3 Daily self-healing patch component."""

def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} expected one match, found {count}")
    return text.replace(old, new, 1)

def apply_daily_core_patch(text):
    old = '''ARENA_LEARNING_FILE = PROFILE_DIR / "arena_learning_model.json"\nARENA_TRACE_FILE = PROFILE_DIR / "arena_battle_trace.jsonl"\n\nDODGE_SETTINGS_FILE = PROFILE_DIR / "dodge_settings.json"\n'''
    new = '''ARENA_LEARNING_FILE = PROFILE_DIR / "arena_learning_model.json"\nARENA_TRACE_FILE = PROFILE_DIR / "arena_battle_trace.jsonl"\nVISION_ADAPTIVE_FILE = PROFILE_DIR / "vision_adaptive.json"\n\nDODGE_SETTINGS_FILE = PROFILE_DIR / "dodge_settings.json"\n'''
    text = _replace_once(text, old, new, "Daily adaptive file constant")
    old = '''    def _daily_check_deadline(self):\n        if self.daily_deadline and time.monotonic() > self.daily_deadline:\n'''
    new = '''    def _daily_save_failure_frame(self, module, stage, ref, detail=""):\n        """Always retain bounded evidence for a real Daily failure."""\n        try:\n            root = self._daily_debug_dir()\n            img = ref.copy()\n            message = str(detail or "")[:150]\n            if message:\n                cv2.rectangle(img, (4, 4), (min(REFERENCE_W - 4, 1500), 43), (0, 0, 0), -1)\n                cv2.putText(\n                    img, message, (12, 30), cv2.FONT_HERSHEY_SIMPLEX,\n                    0.58, (0, 180, 255), 2, cv2.LINE_AA\n                )\n            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")\n            safe_module = re.sub(r"[^A-Za-z0-9_-]+", "_", str(module)).strip("_") or "daily"\n            safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", str(stage)).strip("_") or "failure"\n            path = root / f"FAIL_{stamp}_{safe_module}_{safe_stage}.jpg"\n            cv2.imwrite(str(path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 82])\n            failures = sorted(root.glob("FAIL_*.jpg"), key=lambda p: p.stat().st_mtime)\n            for stale in failures[:-30]:\n                try:\n                    stale.unlink()\n                except Exception:\n                    pass\n            return path\n        except Exception:\n            return None\n\n    def _daily_check_deadline(self):\n        if self.daily_deadline and time.monotonic() > self.daily_deadline:\n'''
    text = _replace_once(text, old, new, "Daily failure evidence helper")
    return text
