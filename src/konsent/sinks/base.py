"""Output interface. Native per-platform drivers plug in here later.

Everything upstream (capture, detection, effects) is platform-agnostic, so
replacing the OBS backend with a signed macOS CMIO extension, a Windows
DirectShow filter, or a direct v4l2loopback writer means implementing this one
class — nothing else in the pipeline changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class FrameSink(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable description of where frames are going."""

    @abstractmethod
    def send(self, frame_bgr: np.ndarray) -> None:
        """Publish one BGR frame."""

    def should_stop(self) -> bool:
        """Sinks that own a window can ask the pipeline to exit."""
        return False

    def close(self) -> None:
        pass

    def __enter__(self) -> "FrameSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
