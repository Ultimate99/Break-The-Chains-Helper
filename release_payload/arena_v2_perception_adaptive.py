#!/usr/bin/env python3
"""V7.3 calibrated-HP accelerator for already-learned catastrophic losses."""


def apply_arena_perception_adaptive_patch(text):
    old = '''        min_elapsed = max(0.0, float(settings.get("min_elapsed_s") or 5.0))\n        threshold = max(0.50, min(0.995, float(settings.get("loss_threshold") or 0.94)))\n        confirm_needed = max(1, int(settings.get("confirm_samples") or 2))\n        if probability is not None and elapsed >= min_elapsed and probability >= threshold:\n'''
    new = '''        min_elapsed = max(0.0, float(settings.get("min_elapsed_s") or 5.0))\n        # Catastrophic mode is NOT a second independent surrender detector. It\n        # only shortens the warm-up when calibrated HP evidence has already\n        # reinforced an >=88% learned loss prediction above. Confirmation is\n        # still required on multiple streamed samples.\n        effective_min_elapsed = min(min_elapsed, 2.5) if catastrophic else min_elapsed\n        threshold = max(0.50, min(0.995, float(settings.get("loss_threshold") or 0.94)))\n        confirm_needed = max(1, int(settings.get("confirm_samples") or 2))\n        if probability is not None and elapsed >= effective_min_elapsed and probability >= threshold:\n'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"catastrophic warm-up anchor expected one match, found {count}")
    text = text.replace(old, new, 1)
    marker = "\n# V7.3 Arena Catastrophic-Loss Accelerator — learned risk + calibrated HP + confirmation build marker\n"
    if marker.strip() not in text:
        text += marker
    return text
