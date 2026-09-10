"""Capture -> detect -> obscure -> publish."""
from __future__ import annotations

import platform
import sys
import threading
import time
from typing import Callable

import cv2
import numpy as np

from . import hotkey
from .config import Config
from .detector import FaceDetector, FaceSignal
from .effects import obscure
from .focus import FocusTracker, Mode
from .sinks import FrameSink, PreviewSink, VirtualCameraSink

# macOS is deliberately absent: asking for CAP_AVFOUNDATION by index opens the
# device but returns no frames on a cold start ("backend is generally available
# but can't be used to capture by index"). CAP_ANY resolves to the same backend
# and works.
_BACKENDS = {
    "Linux": cv2.CAP_V4L2,
    "Windows": cv2.CAP_DSHOW,
}


def open_camera(cfg: Config) -> cv2.VideoCapture:
    backend = _BACKENDS.get(platform.system(), cv2.CAP_ANY)
    cap = cv2.VideoCapture(cfg.camera_index, backend)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera {cfg.camera_index}. "
            "Try --list-cameras, and check that no other app is using it."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, cfg.fps)
    return cap


def list_cameras(limit: int = 6) -> list[int]:
    backend = _BACKENDS.get(platform.system(), cv2.CAP_ANY)
    found = []
    for i in range(limit):
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened() and cap.read()[0]:
            found.append(i)
        cap.release()
    return found


def _draw_hud(
    frame: np.ndarray, sig: FaceSignal, tracker: FocusTracker, fps: float
) -> None:
    c = tracker.cfg
    enter = not tracker.engaged
    yaw, pitch = tracker.angles(sig)
    rows = [
        f"mode {tracker.mode.value}   clarity {tracker.level:0.2f}   {fps:4.1f} fps",
        f"face  {sig.face_ratio:0.3f} / {c.face_ratio_enter if enter else c.face_ratio_exit:0.3f}"
        if sig.found
        else "face  none",
        f"yaw   {yaw:5.1f} / {c.yaw_enter if enter else c.yaw_exit:0.1f}",
        f"pitch {pitch:5.1f} / {c.pitch_enter if enter else c.pitch_exit:0.1f}",
    ]
    colour = (80, 240, 80) if tracker.engaged else (80, 80, 240)
    for i, text in enumerate(rows):
        origin = (12, 28 + i * 24)
        cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 1)


def run(
    cfg: Config,
    preview: bool = False,
    hud: bool = False,
    tracker: FocusTracker | None = None,
    stop_event: "threading.Event | None" = None,
    on_tick: "Callable[[FocusTracker, FaceSignal, float], None] | None" = None,
    quiet: bool = False,
    hotkeys: bool = True,
) -> int:
    """Run until stopped. `tracker`, `stop_event` and `on_tick` let a GUI drive
    and observe the loop; the CLI leaves them unset."""
    cap = open_camera(cfg)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Camera opened but returned no frames.")
    height, width = frame.shape[:2]

    detector = FaceDetector()
    tracker = tracker or FocusTracker(cfg)
    # pynput's macOS backend calls Text Input Source APIs from its listener
    # thread, which assert they are on the main queue and SIGTRAP under an
    # AppKit run loop. The menu bar app uses menu items instead.
    listener = hotkey.start(cfg, tracker) if hotkeys else None

    sink: FrameSink = (
        PreviewSink() if preview else VirtualCameraSink(width, height, cfg.fps)
    )
    if not quiet:
        print(f"[konsent] {width}x{height} -> {sink.name}")
        print(
            f"[konsent] hold {cfg.hotkey_clear} for clear, {cfg.hotkey_blur} for blur"
            if listener
            else "[konsent] running without hotkeys"
        )

    prev = time.monotonic()
    smoothed_fps = float(cfg.fps)
    try:
        with sink:
            while not (stop_event is not None and stop_event.is_set()):
                ok, frame = cap.read()
                if not ok:
                    print("[konsent] camera stopped delivering frames.", file=sys.stderr)
                    break
                if cfg.mirror:
                    frame = cv2.flip(frame, 1)

                now = time.monotonic()
                dt = min(now - prev, 0.25)  # clamp so a stall can't jump the fade
                prev = now
                if dt > 0:
                    smoothed_fps += (1.0 / dt - smoothed_fps) * 0.1

                signal = detector.detect(frame, int(now * 1000))
                level = tracker.update(signal, dt)
                out = obscure(frame, 1.0 - level, cfg.blur_strength)
                if hud:
                    _draw_hud(out, signal, tracker, smoothed_fps)

                sink.send(out)
                if on_tick is not None:
                    on_tick(tracker, signal, smoothed_fps)
                if sink.should_stop():
                    break
    except KeyboardInterrupt:
        print("\n[konsent] stopped.")
    finally:
        cap.release()
        detector.close()
        if listener is not None:
            listener.stop()
    return 0
