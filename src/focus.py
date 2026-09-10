"""Turns raw face signals into a smoothed 0..1 clarity level."""
from __future__ import annotations

from enum import Enum

from .config import Config
from .detector import FaceSignal


class Mode(Enum):
    AUTO = "auto"
    FORCE_CLEAR = "force-clear"
    FORCE_BLUR = "force-blur"


class FocusTracker:
    """Hysteresis + fade, so the picture never flickers on borderline frames."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.mode = Mode.AUTO
        self.engaged = False
        self.level = 0.0  # 0 = fully blurred, 1 = fully clear
        self._missing_for = 0.0

    def angles(self, sig: FaceSignal) -> tuple[float, float]:
        """Head rotation relative to the calibrated neutral pose."""
        return (
            abs(sig.yaw - self.cfg.yaw_offset),
            abs(sig.pitch - self.cfg.pitch_offset),
        )

    def _passes(self, sig: FaceSignal) -> bool:
        c = self.cfg
        yaw, pitch = self.angles(sig)
        if self.engaged:  # looser thresholds while already clear
            return (
                sig.face_ratio >= c.face_ratio_exit
                and yaw <= c.yaw_exit
                and pitch <= c.pitch_exit
            )
        return (
            sig.face_ratio >= c.face_ratio_enter
            and yaw <= c.yaw_enter
            and pitch <= c.pitch_enter
        )

    def update(self, sig: FaceSignal, dt: float) -> float:
        if self.mode is Mode.FORCE_CLEAR:
            target = 1.0
        elif self.mode is Mode.FORCE_BLUR:
            target = 0.0
        else:
            if sig.found:
                self._missing_for = 0.0
                self.engaged = self._passes(sig)
            else:
                self._missing_for += dt
                if self._missing_for >= self.cfg.grace_seconds:
                    self.engaged = False
            target = 1.0 if self.engaged else 0.0

        step = dt / max(self.cfg.fade_seconds, 1e-3)
        if target > self.level:
            self.level = min(target, self.level + step)
        else:
            self.level = max(target, self.level - step)
        return self.level
