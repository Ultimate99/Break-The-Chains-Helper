#!/usr/bin/env python3
"""CI-only import shim for generated-source regression tests.

When test_v730_algorithms.py is executed from release_payload/, Python places
that directory first on sys.path. The installed application normally has
vision_stream.py beside tg_arena_bot.py. Load the repository-root implementation
into this module so the CI import topology matches the installed application.
"""
from pathlib import Path

_source = Path(__file__).resolve().parents[1] / "vision_stream.py"
exec(compile(_source.read_text(encoding="utf-8"), str(_source), "exec"), globals(), globals())
