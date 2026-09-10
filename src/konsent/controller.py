"""Platform-neutral app logic, shared by every tray front end."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from .calibrate import calibrate
from .config import Config, user_config_path
from .focus import FocusTracker, Mode

SETTINGS_TEMPLATE = """# konsent settings. Delete any line to fall back to the default.
face_ratio_enter = 0.30
face_ratio_exit  = 0.24
yaw_enter = 16.0
yaw_exit  = 26.0
pitch_enter = 16.0
pitch_exit  = 26.0
grace_seconds = 0.4
fade_seconds = 0.35
blur_strength = 0.06
"""


def open_in_editor(path: Path) -> None:
    """Open a file in the user's default text editor, on any OS."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-t", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))  # noqa: S606  - Windows only
    else:
        subprocess.run(["xdg-open", str(path)])


class Controller:
    """Owns the capture thread and the state a tray icon renders."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or user_config_path()
        self.cfg = Config.load(self.config_path)
        self.tracker = FocusTracker(self.cfg)
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self.running = False
        self.engaged = False
        self.found = False
        self.fps = 0.0
        self.error: str | None = None

    # --- state --------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return self.tracker.mode

    def set_mode(self, mode: Mode) -> None:
        self.tracker.mode = mode

    def state_name(self) -> str:
        """'clear', 'blurred' or 'off' — what the icon should show."""
        with self._lock:
            if not self.running:
                return "off"
            return "clear" if self.engaged else "blurred"

    def status_text(self) -> str:
        with self._lock:
            if not self.running:
                return "Stopped"
            face = "face detected" if self.found else "no face"
            return f"{'Clear' if self.engaged else 'Blurred'} — {face}, {self.fps:.0f} fps"

    def take_error(self) -> str | None:
        with self._lock:
            error, self.error = self.error, None
            return error

    # --- capture thread -----------------------------------------------------

    def _record(self, tracker: FocusTracker, signal, fps: float) -> None:
        with self._lock:
            self.engaged = tracker.engaged
            self.found = signal.found
            self.fps = fps

    def _worker(self) -> None:
        from .pipeline import run  # imported late: pulls in MediaPipe

        try:
            run(
                self.cfg,
                tracker=self.tracker,
                stop_event=self._stop,
                on_tick=self._record,
                quiet=True,
                hotkeys=False,  # the tray menu provides the overrides
            )
        except Exception as exc:
            with self._lock:
                self.error = str(exc)
        finally:
            with self._lock:
                self.running = False

    def start(self) -> None:
        if self.running:
            return
        mode = self.tracker.mode  # survive a restart
        self.cfg = Config.load(self.config_path)
        self.tracker = FocusTracker(self.cfg)
        self.tracker.mode = mode
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        with self._lock:
            self.running = True
            self.error = None
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        with self._lock:
            self.running = False

    def toggle(self) -> None:
        self.stop() if self.running else self.start()

    # --- actions ------------------------------------------------------------

    def calibrate(self) -> tuple[bool, str]:
        """Stop capturing, measure the neutral pose, reload. Returns (ok, message)."""
        was_running = self.running
        self.stop()  # the capture thread holds the camera
        try:
            ok = calibrate(self.cfg, self.config_path, show=False) == 0
            message = (
                "Not enough face detections. Check your lighting and try again."
                if not ok
                else ""
            )
        except Exception as exc:
            ok, message = False, str(exc)
        if ok:
            self.cfg = Config.load(self.config_path)
            message = (
                f"Neutral pose: yaw {self.cfg.yaw_offset:+.1f}, "
                f"pitch {self.cfg.pitch_offset:+.1f}"
            )
        if was_running:
            self.start()
        return ok, message

    def open_settings(self) -> None:
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(SETTINGS_TEMPLATE)
        open_in_editor(self.config_path)
