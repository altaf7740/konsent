"""Turns raw face signals into a smoothed 0..1 clarity level."""
from __future__ import annotations

from enum import Enum

from .config import Config
from .detector import FaceSignal

# Head-pose estimates jitter by a few degrees frame to frame; this averages
# them over roughly this many seconds before comparing against thresholds.
_SMOOTHING_SECONDS = 0.2


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
        self.smoothed: FaceSignal | None = None
        self._failing_for = 0.0

    def angles(self, sig: FaceSignal) -> tuple[float, float]:
        """Head rotation relative to the calibrated neutral pose."""
        return (
            abs(sig.yaw - self.cfg.yaw_offset),
            abs(sig.pitch - self.cfg.pitch_offset),
        )

    def _smooth(self, sig: FaceSignal, dt: float) -> FaceSignal:
        s = self.smoothed
        if s is None:
            self.smoothed = FaceSignal(True, sig.face_ratio, sig.yaw, sig.pitch)
            return self.smoothed
        a = min(1.0, dt / _SMOOTHING_SECONDS)
        s.face_ratio += a * (sig.face_ratio - s.face_ratio)
        s.yaw += a * (sig.yaw - s.yaw)
        s.pitch += a * (sig.pitch - s.pitch)
        return s

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
            passes = sig.found and self._passes(self._smooth(sig, dt))
            if passes:
                self._failing_for = 0.0
                self.engaged = True
            else:
                # Clear instantly, but blur only once the reason has lasted
                # grace_seconds, so glances and neck shifts don't trigger it.
                self._failing_for += dt
                if self._failing_for >= self.cfg.grace_seconds:
                    self.engaged = False
                    if not sig.found:
                        self.smoothed = None
            target = 1.0 if self.engaged else 0.0

        step = dt / max(self.cfg.fade_seconds, 1e-3)
        if target > self.level:
            self.level = min(target, self.level + step)
        else:
            self.level = max(target, self.level - step)
        return self.level
