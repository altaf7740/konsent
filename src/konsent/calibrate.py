"""Measure the user's neutral head pose, so thresholds mean the same thing on
a laptop lid, an external monitor, or a phone mount."""
from __future__ import annotations

import re
import statistics
import time
from pathlib import Path

import cv2

from .config import Config
from .detector import FaceDetector
from .pipeline import open_camera

_HOLD_SECONDS = 4.0


def _write_offsets(path: Path, yaw: float, pitch: float) -> None:
    lines = [f"yaw_offset = {yaw:.2f}", f"pitch_offset = {pitch:.2f}"]
    if not path.exists():
        path.write_text("# konsent settings\n" + "\n".join(lines) + "\n")
        return
    text = path.read_text()
    for key, line in zip(("yaw_offset", "pitch_offset"), lines):
        pattern = re.compile(rf"^\s*{key}\s*=.*$", re.MULTILINE)
        text = pattern.sub(line, text) if pattern.search(text) else text.rstrip() + "\n" + line + "\n"
    path.write_text(text)


def calibrate(cfg: Config, config_path: Path, show: bool = True) -> int:
    cap = open_camera(cfg)
    detector = FaceDetector()
    window = "konsent calibration"
    if show:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    print("[konsent] Sit where you normally sit and look straight at the camera.")
    yaws: list[float] = []
    pitches: list[float] = []
    start = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= _HOLD_SECONDS:
                break
            ok, frame = cap.read()
            if not ok:
                break
            if cfg.mirror:
                frame = cv2.flip(frame, 1)
            sig = detector.detect(frame, int(time.monotonic() * 1000))
            if sig.found:
                yaws.append(sig.yaw)
                pitches.append(sig.pitch)
            if show:
                msg = f"Look at the camera... {_HOLD_SECONDS - elapsed:0.1f}s"
                if not sig.found:
                    msg = "No face detected"
                cv2.putText(frame, msg, (16, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
                cv2.putText(frame, msg, (16, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                cv2.imshow(window, frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    print("[konsent] calibration cancelled.")
                    return 1
    finally:
        cap.release()
        detector.close()
        if show:
            cv2.destroyWindow(window)

    if len(yaws) < 10:
        print("[konsent] Not enough face detections to calibrate. Check your lighting.")
        return 1

    # Median, not mean: a couple of bad frames shouldn't skew the neutral pose.
    yaw = statistics.median(yaws)
    pitch = statistics.median(pitches)
    _write_offsets(config_path, yaw, pitch)
    print(
        f"[konsent] neutral pose: yaw {yaw:+0.1f}, pitch {pitch:+0.1f} "
        f"(from {len(yaws)} frames) -> written to {config_path}"
    )
    return 0
