"""macOS menu bar front end for konsent."""
from __future__ import annotations

import os
import subprocess
import sys
import threading

import rumps

from . import autostart
from .calibrate import calibrate
from .config import Config, user_config_path
from .focus import FocusTracker, Mode

# Stopped, running-but-blurred, running-and-clear.
GLYPH = {"off": "◌", "blurred": "○", "clear": "●"}

_TEMPLATE = """# konsent settings. Delete any line to fall back to the default.
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


class _State:
    """Written by the capture thread, read by the menu bar on its timer."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.engaged = False
        self.fps = 0.0
        self.found = False
        self.running = False
        self.error: str | None = None


class KonsentApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("konsent", title=GLYPH["off"], quit_button=None)
        self.config_path = user_config_path()
        self.cfg = Config.load(self.config_path)
        self.tracker = FocusTracker(self.cfg)
        self.state = _State()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

        self.status = rumps.MenuItem("Stopped")
        self.toggle = rumps.MenuItem("Start", callback=self.on_toggle)
        self.auto = rumps.MenuItem("Automatic", callback=self.on_auto)
        self.force_clear = rumps.MenuItem("Force clear", callback=self.on_force_clear)
        self.force_blur = rumps.MenuItem("Force blur", callback=self.on_force_blur)
        self.login = rumps.MenuItem("Start at login", callback=self.on_login)
        self.menu = [
            self.status,
            None,
            self.toggle,
            None,
            self.auto,
            self.force_clear,
            self.force_blur,
            None,
            rumps.MenuItem("Calibrate…", callback=self.on_calibrate),
            rumps.MenuItem("Edit settings…", callback=self.on_settings),
            None,
            self.login,
            rumps.MenuItem("Quit", callback=self.on_quit),
        ]
        self.login.state = autostart.is_enabled()

        # Deliberately not started here: the capture thread initialises
        # MediaPipe's GL context, and doing that while AppKit is still setting
        # up the main run loop trips an assertion (SIGTRAP). The first timer
        # tick fires once the run loop is live, which is safe.
        self._pending_start = True
        self._awaiting_auth = False
        self._auth_granted: bool | None = None
        rumps.Timer(self.on_tick, 0.3).start()

    # --- camera permission --------------------------------------------------

    def _begin(self) -> None:
        """Ask for camera access on the main thread, then start capturing.

        Launched by launchd there is no parent terminal whose grant we inherit,
        and OpenCV's own request needs the main run loop from a worker thread,
        which it cannot get ("can not spin main run loop from other thread").
        So we ask via AVFoundation here and tell OpenCV to skip its attempt.
        """
        os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        try:
            import AVFoundation as AVF
        except Exception:
            self.start()
            return

        status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(
            AVF.AVMediaTypeVideo
        )
        if status == 3:  # authorized
            self.start()
        elif status == 0:  # not determined — prompt, without blocking the UI
            self._awaiting_auth = True
            AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVF.AVMediaTypeVideo,
                lambda granted: setattr(self, "_auth_granted", bool(granted)),
            )
        else:  # denied or restricted
            self._camera_denied()

    def _camera_denied(self) -> None:
        rumps.alert(
            "konsent needs camera access",
            "Enable it in System Settings > Privacy & Security > Camera, "
            "then choose Start from the konsent menu.",
        )

    # --- capture thread -----------------------------------------------------

    def _record(self, tracker: FocusTracker, signal, fps: float) -> None:
        with self.state.lock:
            self.state.engaged = tracker.engaged
            self.state.found = signal.found
            self.state.fps = fps

    def _worker(self) -> None:
        from .pipeline import run  # imported late: pulls in MediaPipe

        try:
            run(
                self.cfg,
                tracker=self.tracker,
                stop_event=self._stop,
                on_tick=self._record,
                quiet=True,
                hotkeys=False,
            )
        except Exception as exc:
            with self.state.lock:
                self.state.error = str(exc)
        finally:
            with self.state.lock:
                self.state.running = False

    def start(self) -> None:
        if self.state.running:
            return
        self.cfg = Config.load(self.config_path)
        self.tracker = FocusTracker(self.cfg)
        self.tracker.mode = Mode.AUTO
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        with self.state.lock:
            self.state.running = True
            self.state.error = None
        self._thread.start()
        self.toggle.title = "Stop"

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        with self.state.lock:
            self.state.running = False
        self.toggle.title = "Start"

    # --- menu bar timer (main thread) ---------------------------------------

    def on_tick(self, _timer) -> None:
        if self._pending_start:
            self._pending_start = False
            self._begin()
            return

        if self._awaiting_auth:
            if self._auth_granted is None:
                return  # prompt still on screen
            self._awaiting_auth = False
            self.start() if self._auth_granted else self._camera_denied()
            return

        with self.state.lock:
            running, engaged, fps, found = (
                self.state.running,
                self.state.engaged,
                self.state.fps,
                self.state.found,
            )
            error, self.state.error = self.state.error, None

        if error:
            self.stop()
            rumps.alert("konsent could not start", error)
            return

        if not running:
            self.title = GLYPH["off"]
            self.status.title = "Stopped"
            self.toggle.title = "Start"
        else:
            self.title = GLYPH["clear" if engaged else "blurred"]
            face = "face detected" if found else "no face"
            self.status.title = f"{'Clear' if engaged else 'Blurred'} — {face}, {fps:.0f} fps"

        mode = self.tracker.mode
        self.auto.state = mode is Mode.AUTO
        self.force_clear.state = mode is Mode.FORCE_CLEAR
        self.force_blur.state = mode is Mode.FORCE_BLUR

    # --- menu actions -------------------------------------------------------

    def on_toggle(self, _) -> None:
        self.stop() if self.state.running else self.start()

    def on_auto(self, _) -> None:
        self.tracker.mode = Mode.AUTO

    def on_force_clear(self, _) -> None:
        self.tracker.mode = Mode.FORCE_CLEAR

    def on_force_blur(self, _) -> None:
        self.tracker.mode = Mode.FORCE_BLUR

    def on_calibrate(self, _) -> None:
        was_running = self.state.running
        self.stop()  # the capture thread holds the camera
        rumps.alert(
            "Calibrate konsent",
            "Sit where you normally sit and look straight at the camera.\n\n"
            "Click OK, then hold still for about four seconds.",
        )
        try:
            ok = calibrate(self.cfg, self.config_path, show=False) == 0
        except Exception as exc:
            ok = False
            rumps.alert("Calibration failed", str(exc))
        if ok:
            self.cfg = Config.load(self.config_path)
            rumps.alert(
                "Calibration saved",
                f"Neutral pose: yaw {self.cfg.yaw_offset:+.1f}, "
                f"pitch {self.cfg.pitch_offset:+.1f}",
            )
        if was_running:
            self.start()

    def on_settings(self, _) -> None:
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(_TEMPLATE)
        subprocess.run(["open", "-t", str(self.config_path)])
        rumps.alert(
            "Settings",
            "Save the file, then choose Stop and Start to apply your changes.",
        )

    def on_login(self, _) -> None:
        if self.login.state:
            autostart.disable()
        else:
            autostart.enable()
        self.login.state = autostart.is_enabled()

    def on_quit(self, _) -> None:
        self.stop()
        rumps.quit_application()


def main() -> int:
    if sys.platform != "darwin":
        print(
            "The menu bar app is macOS only. Use `konsent` instead.", file=sys.stderr
        )
        return 1
    try:  # menu bar only, no Dock icon
        from AppKit import NSApplication

        NSApplication.sharedApplication().setActivationPolicy_(1)
    except Exception:
        pass
    KonsentApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
