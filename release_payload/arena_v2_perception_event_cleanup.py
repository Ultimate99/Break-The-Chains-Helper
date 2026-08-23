#!/usr/bin/env python3
"""Small readability cleanup for the V7.3 event-memory source patch."""


def apply_arena_perception_event_cleanup(text):
    old = '''        self._learning_last_enemy_event_sig = _arena_event_signature(self._phone_safe_ref_for_event() if hasattr(self, "_phone_safe_ref_for_event") else None) if False else None\n'''
    new = '''        self._learning_last_enemy_event_sig = None\n'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"event baseline cleanup expected one match, found {count}")
    return text.replace(old, new, 1)
