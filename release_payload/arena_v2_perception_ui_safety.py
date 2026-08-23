#!/usr/bin/env python3
"""Runtime edge-case hardening for the V7.3 Perception page."""


def apply_arena_perception_ui_safety_patch(text):
    old = '''            messagebox.showinfo(\n                "Arena Perception Test",\n                f"Power: {power_text}\\nPower OCR confidence: {conf:.0f}%" + ("" if conf is not None else " (unknown)") +\n                f"\\nAlly HP: {ally_text}\\nEnemy HP: {enemy_text}\\nNearest event: {event_text}"\n            )\n'''
    new = '''            conf_text = f"{conf:.0f}%" if conf is not None else "UNKNOWN"\n            messagebox.showinfo(\n                "Arena Perception Test",\n                f"Power: {power_text}\\nPower OCR confidence: {conf_text}"\n                f"\\nAlly HP: {ally_text}\\nEnemy HP: {enemy_text}\\nNearest event: {event_text}"\n            )\n'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Perception UI confidence hardening expected one match, found {count}")
    return text.replace(old, new, 1)
