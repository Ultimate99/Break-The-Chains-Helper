#!/usr/bin/env python3
"""CI-only transport stub for generated-source algorithm tests.

The V7.3 regression suite exercises learning, Pilot, Daily vision state,
Power/HP parsing and event clustering. It does not start ADB or Fast Vision.
Provide only the imported transport symbols so those algorithms can be loaded
and tested independently from device/FFmpeg availability.
"""

class VisionStream:
    def __init__(self, *args, **kwargs):
        self.running = False
        self.fps = 0.0
        self.last_error = None

    def start(self, *args, **kwargs):
        return False

    def stop(self):
        self.running = False

    def get_latest(self):
        return None, None, None


class AdbTapShell:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return False

    def stop(self):
        pass

    def tap(self, *args, **kwargs):
        return False


def find_ffmpeg():
    return None


def query_device_size(*args, **kwargs):
    return None
