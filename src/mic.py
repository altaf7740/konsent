"""System microphone mute, so blurring also silences you.

Every platform exposes this differently and none of them through a library we
already depend on, so this shells out to the tool each OS ships with. A failure
here must never take the video down: the muter disables itself and records why.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _run(args: list[str]) -> str:
    """Run a short command, returning stdout. Raises on failure."""
    out = subprocess.run(
        args, capture_output=True, text=True, timeout=5, check=True
    )
    return out.stdout.strip()


class MicMuter:
    """Mutes and unmutes the default input device, idempotently.

    `set_muted` is called every frame, so it only shells out on a change.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.muted = False
        self.error: str | None = None
        self._restore_volume: float | None = None  # macOS only
        if enabled and not self._supported():
            self.enabled = False
            self.error = (
                "Microphone muting is not supported on this platform; "
                "set mute_mic = false to silence this message."
            )

    @property
    def name(self) -> str:
        if self.error:
            return f"mic muting off ({self.error})"
        return "mic muting on" if self.enabled else "mic muting off"

    @staticmethod
    def _supported() -> bool:
        if sys.platform == "darwin":
            return True
        if os.name == "nt":
            return False  # no built-in CLI for the capture device
        return True  # PulseAudio / PipeWire via pactl

    def set_muted(self, muted: bool) -> None:
        if not self.enabled or muted == self.muted:
            return
        try:
            self._apply(muted)
        except Exception as exc:  # a missing pactl, a locked device, a timeout
            self.enabled = False
            self.error = f"could not change the microphone: {exc}"
            return
        self.muted = muted

    def _apply(self, muted: bool) -> None:
        if sys.platform == "darwin":
            self._apply_macos(muted)
        else:
            state = "1" if muted else "0"
            _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", state])

    def _apply_macos(self, muted: bool) -> None:
        """macOS has no input mute switch, only an input volume."""
        if muted:
            current = float(_run(["osascript", "-e", "input volume of (get volume settings)"]))
            # -1 means "no input device"; anything at 0 is already silent, and
            # restoring to it later would be indistinguishable from muting.
            self._restore_volume = current if current > 0 else None
            _run(["osascript", "-e", "set volume input volume 0"])
        elif self._restore_volume is not None:
            _run(["osascript", "-e", f"set volume input volume {self._restore_volume:.0f}"])
            self._restore_volume = None

    def close(self) -> None:
        """Always hand the microphone back, however the pipeline ended —
        including after an error disabled us mid-way."""
        if not self.muted:
            return
        try:
            self._apply(False)
        except Exception:
            pass
        self.muted = False

    def __enter__(self) -> "MicMuter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
