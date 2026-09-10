"""Menu bar front end for macOS, via rumps."""
from __future__ import annotations

import os

import rumps

from ..autostart import disable, enable, is_enabled
from ..controller import Controller
from ..focus import Mode
from .icons import GLYPH


class MacTray(rumps.App):
    def __init__(self) -> None:
        super().__init__("konsent", title=GLYPH["off"], quit_button=None)
        self.controller = Controller()

        self.status = rumps.MenuItem("Stopped")
        self.toggle = rumps.MenuItem("Start", callback=self.on_toggle)
        self.auto = rumps.MenuItem("Automatic", callback=self.on_mode(Mode.AUTO))
        self.force_clear = rumps.MenuItem(
            "Force clear", callback=self.on_mode(Mode.FORCE_CLEAR)
        )
        self.force_blur = rumps.MenuItem(
            "Force blur", callback=self.on_mode(Mode.FORCE_BLUR)
        )
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
        self.login.state = is_enabled()

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
        """
        os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        try:
            import AVFoundation as AVF
        except Exception:
            self.controller.start()
            return

        status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(
            AVF.AVMediaTypeVideo
        )
        if status == 3:  # authorized
            self.controller.start()
        elif status == 0:  # not determined — prompt without blocking the UI
            self._awaiting_auth = True
            AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVF.AVMediaTypeVideo,
                lambda granted: setattr(self, "_auth_granted", bool(granted)),
            )
        else:
            self._camera_denied()

    def _camera_denied(self) -> None:
        rumps.alert(
            "konsent needs camera access",
            "Enable it in System Settings > Privacy & Security > Camera, "
            "then choose Start from the konsent menu.",
        )

    # --- timer (main thread) ------------------------------------------------

    def on_tick(self, _timer) -> None:
        if self._pending_start:
            self._pending_start = False
            self._begin()
            return

        if self._awaiting_auth:
            if self._auth_granted is None:
                return  # prompt still on screen
            self._awaiting_auth = False
            self.controller.start() if self._auth_granted else self._camera_denied()
            return

        error = self.controller.take_error()
        if error:
            self.controller.stop()
            rumps.alert("konsent could not start", error)
            return

        self.title = GLYPH[self.controller.state_name()]
        self.status.title = self.controller.status_text()
        self.toggle.title = "Stop" if self.controller.running else "Start"

        mode = self.controller.mode
        self.auto.state = mode is Mode.AUTO
        self.force_clear.state = mode is Mode.FORCE_CLEAR
        self.force_blur.state = mode is Mode.FORCE_BLUR

    # --- menu actions -------------------------------------------------------

    def on_toggle(self, _) -> None:
        self.controller.toggle()

    def on_mode(self, mode: Mode):
        return lambda _: self.controller.set_mode(mode)

    def on_calibrate(self, _) -> None:
        rumps.alert(
            "Calibrate konsent",
            "Sit where you normally sit and look straight at the camera.\n\n"
            "Click OK, then hold still for about four seconds.",
        )
        ok, message = self.controller.calibrate()
        rumps.alert("Calibration saved" if ok else "Calibration failed", message)

    def on_settings(self, _) -> None:
        self.controller.open_settings()
        rumps.alert(
            "Settings",
            "Save the file, then choose Stop and Start to apply your changes.",
        )

    def on_login(self, _) -> None:
        disable() if self.login.state else enable()
        self.login.state = is_enabled()

    def on_quit(self, _) -> None:
        self.controller.stop()
        rumps.quit_application()


def run() -> int:
    try:  # menu bar only, no Dock icon
        from AppKit import NSApplication

        NSApplication.sharedApplication().setActivationPolicy_(1)
    except Exception:
        pass
    MacTray().run()
    return 0
