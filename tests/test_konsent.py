import time

import numpy as np
import pytest

from konsent.config import Config
from konsent.detector import FaceDetector, FaceSignal, _normalize_angle
from konsent.effects import obscure
from konsent.focus import FocusTracker, Mode


def facing(ratio):
    return FaceSignal(found=True, face_ratio=ratio, yaw=0.0, pitch=0.0)


def settle(tracker, sig, seconds=2.0, dt=1 / 30):
    for _ in range(int(seconds / dt)):
        tracker.update(sig, dt)
    return tracker.level


# --- hysteresis -------------------------------------------------------------

def test_leaning_in_clears_the_picture():
    t = FocusTracker(Config())
    assert settle(t, facing(0.40)) == pytest.approx(1.0)
    assert t.engaged


def test_sitting_back_blurs_the_picture():
    t = FocusTracker(Config())
    settle(t, facing(0.40))
    assert settle(t, facing(0.10)) == pytest.approx(0.0)
    assert not t.engaged


def test_between_thresholds_does_not_engage_from_blurred():
    cfg = Config()
    mid = (cfg.face_ratio_enter + cfg.face_ratio_exit) / 2
    t = FocusTracker(cfg)
    assert settle(t, facing(mid)) == pytest.approx(0.0)


def test_between_thresholds_holds_once_engaged():
    """The whole point of hysteresis: no flicker when hovering at the boundary."""
    cfg = Config()
    mid = (cfg.face_ratio_enter + cfg.face_ratio_exit) / 2
    t = FocusTracker(cfg)
    settle(t, facing(0.40))
    assert settle(t, facing(mid)) == pytest.approx(1.0)


def test_turning_away_blurs_even_when_close():
    cfg = Config()
    t = FocusTracker(cfg)
    settle(t, facing(0.40))
    turned = FaceSignal(found=True, face_ratio=0.40, yaw=cfg.yaw_exit + 5, pitch=0.0)
    assert settle(t, turned) == pytest.approx(0.0)


# --- timing -----------------------------------------------------------------

def test_fade_is_gradual_not_instant():
    t = FocusTracker(Config())
    t.update(facing(0.40), 1 / 30)
    assert 0.0 < t.level < 1.0


def test_brief_detector_dropout_does_not_blur():
    cfg = Config()
    t = FocusTracker(cfg)
    settle(t, facing(0.40))
    for _ in range(3):
        t.update(FaceSignal(found=False), cfg.grace_seconds / 8)
    assert t.engaged


def test_sustained_absence_blurs():
    cfg = Config()
    t = FocusTracker(cfg)
    settle(t, facing(0.40))
    assert settle(t, FaceSignal(found=False)) == pytest.approx(0.0)


# --- overrides --------------------------------------------------------------

def test_force_clear_beats_an_absent_face():
    t = FocusTracker(Config())
    t.mode = Mode.FORCE_CLEAR
    assert settle(t, FaceSignal(found=False)) == pytest.approx(1.0)


def test_force_blur_beats_a_close_face():
    t = FocusTracker(Config())
    t.mode = Mode.FORCE_BLUR
    assert settle(t, facing(0.40)) == pytest.approx(0.0)


# --- effect -----------------------------------------------------------------

def test_zero_amount_leaves_the_frame_untouched():
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    assert obscure(frame, 0.0, 0.06) is frame


def test_full_blur_destroys_detail_but_keeps_format():
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    out = obscure(frame, 1.0, 0.06)
    assert out.shape == frame.shape and out.dtype == frame.dtype
    assert out.std() < frame.std() / 4


def test_blur_holds_a_30fps_budget():
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    obscure(frame, 1.0, 0.06)  # warm up
    start = time.perf_counter()
    for _ in range(20):
        obscure(frame, 1.0, 0.06)
    per_frame_ms = (time.perf_counter() - start) / 20 * 1000
    assert per_frame_ms < 33, f"{per_frame_ms:.1f}ms/frame"


# --- detector ---------------------------------------------------------------

def test_normalize_angle_unwraps_forward_facing_pitch():
    assert _normalize_angle(178.0) == pytest.approx(-2.0)
    assert _normalize_angle(-179.0) == pytest.approx(1.0)
    assert _normalize_angle(12.0) == pytest.approx(12.0)


def test_detector_reports_no_face_on_an_empty_frame():
    d = FaceDetector()
    try:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        assert d.detect(blank, 0).found is False
    finally:
        d.close()


def test_detector_tolerates_non_increasing_timestamps():
    d = FaceDetector()
    try:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        d.detect(blank, 100)
        d.detect(blank, 100)
        d.detect(blank, 50)
    finally:
        d.close()


# --- calibration ------------------------------------------------------------

def test_offsets_shift_what_counts_as_neutral():
    """A laptop camera reads every face as pitched down; the offset cancels it."""
    cfg = Config()
    cfg.pitch_offset = 24.0
    t = FocusTracker(cfg)
    slouched_but_looking = FaceSignal(found=True, face_ratio=0.40, yaw=0.0, pitch=24.0)
    assert settle(t, slouched_but_looking) == pytest.approx(1.0)


def test_offsets_do_not_excuse_actually_looking_away():
    cfg = Config()
    cfg.pitch_offset = 24.0
    t = FocusTracker(cfg)
    away = FaceSignal(found=True, face_ratio=0.40, yaw=0.0, pitch=24.0 + cfg.pitch_enter + 5)
    assert settle(t, away) == pytest.approx(0.0)


def test_angles_are_symmetric_around_the_offset():
    cfg = Config()
    cfg.yaw_offset = 10.0
    t = FocusTracker(cfg)
    left = t.angles(FaceSignal(found=True, yaw=10.0 - 7))[0]
    right = t.angles(FaceSignal(found=True, yaw=10.0 + 7))[0]
    assert left == pytest.approx(right) == pytest.approx(7.0)


def test_calibration_creates_a_config_file(tmp_path):
    from konsent.calibrate import _write_offsets

    path = tmp_path / "config.toml"
    _write_offsets(path, 1.5, -22.25)
    assert Config.load(path).pitch_offset == pytest.approx(-22.25)


def test_calibration_rewrites_offsets_without_losing_other_settings(tmp_path):
    from konsent.calibrate import _write_offsets

    path = tmp_path / "config.toml"
    path.write_text("camera_index = 3\nyaw_offset = 99.0\npitch_offset = 99.0\nfps = 24\n")
    _write_offsets(path, 1.0, 2.0)
    cfg = Config.load(path)
    assert (cfg.yaw_offset, cfg.pitch_offset) == (1.0, 2.0)
    assert (cfg.camera_index, cfg.fps) == (3, 24)


# --- autostart --------------------------------------------------------------

def test_login_plist_is_valid_and_runs_at_load():
    import plistlib
    from pathlib import Path
    from konsent import autostart

    data = plistlib.loads(autostart.build_plist(Path("/opt/konsent/bin/konsent-app")).encode())
    assert data["Label"] == autostart.LABEL
    assert data["RunAtLoad"] is True
    assert data["ProgramArguments"] == ["/opt/konsent/bin/konsent-app"]


def test_login_plist_falls_back_to_module_invocation():
    """If the console script is missing we must still name something runnable."""
    import plistlib
    from pathlib import Path
    from konsent import autostart

    data = plistlib.loads(autostart.build_plist(Path("/usr/bin/python3")).encode())
    assert data["ProgramArguments"] == ["/usr/bin/python3", "-m", "konsent.app"]


def test_config_path_is_absolute():
    """launchd starts us in '/', so a relative path would lose the calibration."""
    from konsent.config import user_config_path

    assert user_config_path().is_absolute()
