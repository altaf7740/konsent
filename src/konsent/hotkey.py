"""Global hotkeys for manually overriding the automatic decision."""
from __future__ import annotations

import sys

from .config import Config
from .focus import FocusTracker, Mode


def start(cfg: Config, tracker: FocusTracker):
    """Returns the running listener, or None if hotkeys are unavailable."""
    try:
        from pynput import keyboard
    except Exception as exc:  # pragma: no cover - platform dependent
        print(f"[konsent] hotkeys unavailable: {exc}", file=sys.stderr)
        return None

    def toggle(mode: Mode):
        def handler():
            tracker.mode = Mode.AUTO if tracker.mode is mode else mode
            print(f"[konsent] mode: {tracker.mode.value}")

        return handler

    try:
        listener = keyboard.GlobalHotKeys(
            {
                cfg.hotkey_clear: toggle(Mode.FORCE_CLEAR),
                cfg.hotkey_blur: toggle(Mode.FORCE_BLUR),
            }
        )
        listener.start()
        return listener
    except Exception as exc:  # pragma: no cover - needs OS permission
        print(
            f"[konsent] could not register hotkeys ({exc}).\n"
            "  On macOS grant Accessibility permission to your terminal in\n"
            "  System Settings > Privacy & Security > Accessibility.",
            file=sys.stderr,
        )
        return None
