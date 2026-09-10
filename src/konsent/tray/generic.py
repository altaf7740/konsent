"""Tray front end for Linux and Windows, via pystray."""
from __future__ import annotations

import threading

import pystray
from pystray import Menu, MenuItem

from ..autostart import disable, enable, is_enabled
from ..controller import Controller
from ..focus import Mode
from .icons import make_icon

_POLL_SECONDS = 0.5


class GenericTray:
    def __init__(self) -> None:
        self.controller = Controller()
        self._state = "off"
        self.icon = pystray.Icon(
            "konsent",
            icon=make_icon("off"),
            title="konsent",
            menu=Menu(
                MenuItem(lambda _: self.controller.status_text(), None, enabled=False),
                Menu.SEPARATOR,
                MenuItem(
                    lambda _: "Stop" if self.controller.running else "Start",
                    self.on_toggle,
                ),
                Menu.SEPARATOR,
                MenuItem(
                    "Automatic",
                    self.on_mode(Mode.AUTO),
                    checked=lambda _: self.controller.mode is Mode.AUTO,
                    radio=True,
                ),
                MenuItem(
                    "Force clear",
                    self.on_mode(Mode.FORCE_CLEAR),
                    checked=lambda _: self.controller.mode is Mode.FORCE_CLEAR,
                    radio=True,
                ),
                MenuItem(
                    "Force blur",
                    self.on_mode(Mode.FORCE_BLUR),
                    checked=lambda _: self.controller.mode is Mode.FORCE_BLUR,
                    radio=True,
                ),
                Menu.SEPARATOR,
                MenuItem("Calibrate", self.on_calibrate),
                MenuItem("Edit settings", self.on_settings),
                Menu.SEPARATOR,
                MenuItem(
                    "Start at login", self.on_login, checked=lambda _: is_enabled()
                ),
                MenuItem("Quit", self.on_quit),
            ),
        )

    # --- polling ------------------------------------------------------------

    def _poll(self) -> None:
        while not self._done.is_set():
            error = self.controller.take_error()
            if error:
                self.controller.stop()
                self.icon.notify(error, "konsent could not start")
            state = self.controller.state_name()
            if state != self._state:
                self._state = state
                self.icon.icon = make_icon(state)
            self.icon.title = f"konsent — {self.controller.status_text()}"
            self.icon.update_menu()
            self._done.wait(_POLL_SECONDS)

    # --- menu actions -------------------------------------------------------

    def on_toggle(self, *_):
        self.controller.toggle()

    def on_mode(self, mode: Mode):
        return lambda *_: self.controller.set_mode(mode)

    def on_calibrate(self, *_):
        self.icon.notify(
            "Look straight at the camera for about four seconds.", "Calibrating"
        )
        ok, message = self.controller.calibrate()
        self.icon.notify(message, "Calibration saved" if ok else "Calibration failed")

    def on_settings(self, *_):
        self.controller.open_settings()

    def on_login(self, *_):
        disable() if is_enabled() else enable()

    def on_quit(self, *_):
        self._done.set()
        self.controller.stop()
        self.icon.stop()

    # --- lifecycle ----------------------------------------------------------

    def run(self) -> int:
        self._done = threading.Event()
        # Start capture only once the tray is up, and poll from a worker so the
        # UI thread stays free for the platform's own event loop.
        self.icon.run(setup=self._setup)
        return 0

    def _setup(self, icon) -> None:
        icon.visible = True
        self.controller.start()
        threading.Thread(target=self._poll, daemon=True).start()


def run() -> int:
    return GenericTray().run()
