"""Tray front ends. macOS uses rumps; everything else uses pystray."""
from __future__ import annotations

import sys


def run() -> int:
    if sys.platform == "darwin":
        from .mac import run as _run
    else:
        from .generic import run as _run
    return _run()
