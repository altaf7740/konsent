"""Virtual camera output via pyvirtualcam (OBS backend on macOS/Windows,
v4l2loopback on Linux)."""
from __future__ import annotations

import platform

import numpy as np
import pyvirtualcam

from .base import FrameSink

_SETUP_HINT = {
    "Darwin": (
        "Install OBS Studio (https://obsproject.com) and open it once, then click "
        "'Start Virtual Camera' in the Controls panel to register the device. "
        "You can close OBS afterwards on most versions."
    ),
    "Windows": (
        "Install OBS Studio (https://obsproject.com) and open it once so the "
        "virtual camera driver gets registered."
    ),
    "Linux": (
        "Load the loopback module:\n"
        "  sudo apt install v4l2loopback-dkms\n"
        "  sudo modprobe v4l2loopback devices=1 video_nr=10 "
        "card_label='konsent' exclusive_caps=1"
    ),
}


class VirtualCameraSink(FrameSink):
    def __init__(self, width: int, height: int, fps: int) -> None:
        try:
            self._cam = pyvirtualcam.Camera(
                width=width, height=height, fps=fps, fmt=pyvirtualcam.PixelFormat.BGR
            )
        except Exception as exc:
            hint = _SETUP_HINT.get(platform.system(), "")
            raise RuntimeError(
                f"Could not open a virtual camera: {exc}\n\n{hint}"
            ) from exc

    @property
    def name(self) -> str:
        return f"virtual camera '{self._cam.device}' ({self._cam.width}x{self._cam.height})"

    def send(self, frame_bgr: np.ndarray) -> None:
        self._cam.send(frame_bgr)
        self._cam.sleep_until_next_frame()

    def close(self) -> None:
        self._cam.close()
