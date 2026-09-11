"""Tunable settings, optionally overridden by a TOML file."""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


def user_config_path() -> Path:
    """One canonical location, so a login-launched app and the CLI agree.

    A relative path would resolve against the working directory, which is "/"
    when launchd starts us — silently losing the calibration offsets.
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "konsent" / "config.toml"


def default_config_path() -> Path:
    """Prefer a config.toml in the current directory (e.g. a project checkout)
    over the OS-wide location, so `uv run konsent` picks up local edits without
    needing --config."""
    local = Path("config.toml")
    return local if local.exists() else user_config_path()


@dataclass
class Config:
    # --- capture ---
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    mirror: bool = False

    # --- "am I focusing on the camera?" ---
    # Fraction of frame height covered by the face. Entering focus demands a
    # bigger face than holding it, so small movements don't flip the state.
    face_ratio_enter: float = 0.30
    face_ratio_exit: float = 0.24
    # Head rotation away from the camera, in degrees, measured relative to the
    # offsets below. Absolute pose depends on where the camera physically sits
    # (a laptop lid is well below eye level), so these are set by --calibrate.
    yaw_offset: float = 0.0
    pitch_offset: float = 0.0
    yaw_enter: float = 16.0
    yaw_exit: float = 26.0
    pitch_enter: float = 16.0
    pitch_exit: float = 26.0
    # How long you may look away, lean back or drop out of view before we blur.
    grace_seconds: float = 0.4

    # --- look ---
    fade_seconds: float = 0.35
    blur_strength: float = 0.06  # max blur sigma as a fraction of frame width

    # --- override hotkeys (pynput syntax) ---
    hotkey_clear: str = "<ctrl>+<alt>+c"
    hotkey_blur: str = "<ctrl>+<alt>+b"

    @classmethod
    def load(cls, path: Path | None) -> "Config":
        cfg = cls()
        if path is None or not path.exists():
            return cfg
        data = tomllib.loads(path.read_text())
        known = {f.name for f in fields(cls)}
        for section in data.values():
            if not isinstance(section, dict):
                continue
            for key, value in section.items():
                if key in known:
                    setattr(cfg, key, value)
        for key, value in data.items():
            if key in known:
                setattr(cfg, key, value)
        return cfg
