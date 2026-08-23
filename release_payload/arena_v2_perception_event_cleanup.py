#!/usr/bin/env python3
"""Idempotent readability normalization for V7.3 event-memory source."""


def apply_arena_perception_event_cleanup(text):
    old = '''        self._learning_last_enemy_event_sig = _arena_event_signature(self._phone_safe_ref_for_event() if hasattr(self, "_phone_safe_ref_for_event") else None) if False else None\n'''
    new = '''        self._learning_last_enemy_event_sig = None\n'''
    count = text.count(old)
    if count == 1:
        text = text.replace(old, new, 1)
    elif count > 1:
        raise RuntimeError(f"event baseline cleanup found duplicate scaffolding: {count}")
    # Idempotent by design: some build orders may already contain the clean
    # assignment. The quality gate below still rejects any surviving dead path.
    if "_phone_safe_ref_for_event" in text or "if False else None" in text:
        raise RuntimeError("event baseline cleanup left dead capture scaffolding")
    return text
