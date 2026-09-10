"""Face proximity and head-pose estimation via MediaPipe Face Landmarker."""
from __future__ import annotations

import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def model_dir() -> Path:
    """Cache the model outside the repo, so an installed copy works too."""
    override = os.environ.get("KONSENT_MODEL_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "konsent"


MODEL_PATH = model_dir() / "face_landmarker.task"

# Landmark indices into the 478-point face mesh, paired with the generic 3D head
# model below so solvePnP can recover head rotation.
_POSE_LANDMARKS = (1, 152, 33, 263, 61, 291)
_MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),        # nose tip
        (0.0, -63.6, -12.5),    # chin
        (-43.3, 32.7, -26.0),   # left eye, outer corner
        (43.3, 32.7, -26.0),    # right eye, outer corner
        (-28.9, -28.9, -24.1),  # left mouth corner
        (28.9, -28.9, -24.1),   # right mouth corner
    ],
    dtype=np.float64,
)


@dataclass
class FaceSignal:
    found: bool
    face_ratio: float = 0.0  # face height as a fraction of frame height
    yaw: float = 0.0         # signed degrees; offset is applied downstream
    pitch: float = 0.0


def ensure_model(path: Path | None = None) -> Path:
    path = path or MODEL_PATH
    if not path.exists():
        print(f"[konsent] downloading face model to {path} ...")
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, path)
    return path


def _normalize_angle(deg: float) -> float:
    """RQDecomp3x3 reports pitch near ±180 for a forward-facing head."""
    if deg > 90:
        deg -= 180
    elif deg < -90:
        deg += 180
    return deg


class FaceDetector:
    def __init__(self, model_path: Path | None = None) -> None:
        path = ensure_model(model_path)
        self._landmarker = FaceLandmarker.create_from_options(
            FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(path)),
                running_mode=RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        self._last_ts = -1

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> FaceSignal:
        # MediaPipe requires strictly increasing timestamps in VIDEO mode.
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return FaceSignal(found=False)

        marks = result.face_landmarks[0]
        ys = [m.y for m in marks]
        face_ratio = float(max(ys) - min(ys))

        h, w = frame_bgr.shape[:2]
        image_points = np.array(
            [(marks[i].x * w, marks[i].y * h) for i in _POSE_LANDMARKS],
            dtype=np.float64,
        )
        camera_matrix = np.array(
            [[float(w), 0, w / 2.0], [0, float(w), h / 2.0], [0, 0, 1]],
            dtype=np.float64,
        )
        ok, rvec, _ = cv2.solvePnP(
            _MODEL_POINTS,
            image_points,
            camera_matrix,
            np.zeros((4, 1)),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return FaceSignal(found=True, face_ratio=face_ratio)

        rmat, _ = cv2.Rodrigues(rvec)
        pitch, yaw, _roll = cv2.RQDecomp3x3(rmat)[0]
        return FaceSignal(
            found=True,
            face_ratio=face_ratio,
            yaw=_normalize_angle(yaw),
            pitch=_normalize_angle(pitch),
        )

    def close(self) -> None:
        self._landmarker.close()
