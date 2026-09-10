"""On-screen preview window, for tuning thresholds without a virtual camera."""
from __future__ import annotations

import cv2
import numpy as np

from .base import FrameSink

_WINDOW = "konsent (press q to quit)"


class PreviewSink(FrameSink):
    def __init__(self) -> None:
        self._stop = False
        cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)

    @property
    def name(self) -> str:
        return "preview window"

    def send(self, frame_bgr: np.ndarray) -> None:
        cv2.imshow(_WINDOW, frame_bgr)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            self._stop = True

    def should_stop(self) -> bool:
        return self._stop

    def close(self) -> None:
        cv2.destroyWindow(_WINDOW)
