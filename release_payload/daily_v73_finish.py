#!/usr/bin/env python3
"""V7.3 Daily self-healing recovery patch component."""

def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} expected one match, found {count}")
    return text.replace(old, new, 1)

def apply_daily_finish_patch(text):
    old = '''                    if not ok:\n                        if final_ref is not None:\n                            self._daily_save_debug_frame(module,"destination_failed",final_ref)\n                        self._daily_set_status(module,"DESTINATION FAIL")\n                        raise RuntimeError(f"Could not verify {module} destination ({detail})")\n'''
    new = '''                    if not ok:\n                        if final_ref is not None:\n                            self._daily_save_debug_frame(module,"destination_failed",final_ref)\n                            saved=self._daily_save_failure_frame(\n                                module,"destination_failed",final_ref,detail\n                            )\n                            if saved:\n                                self.add_log(f"Daily {module}: destination failure evidence saved {saved.name}")\n                        self._daily_set_status(module,"DESTINATION FAIL")\n                        raise RuntimeError(f"Could not safely verify {module} destination ({detail})")\n'''
    text = _replace_once(text, old, new, "Daily destination failure evidence")
    marker = "\n# V7.3 Daily Self-Healing Vision — OCR-verified adaptive fingerprints + bounded recovery build marker\n"
    if marker.strip() not in text:
        text += marker
    return text
