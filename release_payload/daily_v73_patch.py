#!/usr/bin/env python3
"""Readable V7.3 Daily self-healing source patch."""
from daily_v73_core import apply_daily_core_patch
from daily_v73_identify import apply_daily_identify_patch
from daily_v73_anchor import apply_daily_anchor_patch
from daily_v73_start import apply_daily_start_patch
from daily_v73_route import apply_daily_route_patch
from daily_v73_finish import apply_daily_finish_patch


def apply_daily_v73_patch(text):
    text = apply_daily_core_patch(text)
    text = apply_daily_identify_patch(text)
    text = apply_daily_anchor_patch(text)
    text = apply_daily_start_patch(text)
    text = apply_daily_route_patch(text)
    text = apply_daily_finish_patch(text)
    return text
