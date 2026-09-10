"""Frame obscuring effects."""
from __future__ import annotations

import cv2
import numpy as np


def obscure(frame: np.ndarray, amount: float, strength: float) -> np.ndarray:
    """Gaussian defocus. `amount` 0 = untouched, 1 = fully obscured.

    Heavy blur is done by downscaling first: a large-sigma GaussianBlur at full
    resolution is far too slow to hold 30 fps.
    """
    if amount <= 0.001:
        return frame
    h, w = frame.shape[:2]
    sigma = strength * w * amount
    if sigma < 0.5:
        return frame

    scale = min(1.0, 4.0 / sigma)
    if scale < 1.0:
        small = cv2.resize(
            frame,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        s = sigma * scale
        k = max(3, int(round(s * 4)) | 1)
        small = cv2.GaussianBlur(small, (k, k), s)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    k = max(3, int(round(sigma * 4)) | 1)
    return cv2.GaussianBlur(frame, (k, k), sigma)
