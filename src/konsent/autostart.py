"""Start konsent at login via a macOS LaunchAgent."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LABEL = "com.konsent.menubar"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"


def executable() -> Path:
    """The installed console script, so login doesn't depend on uv being on PATH."""
    candidate = Path(sys.executable).parent / "konsent-app"
    return candidate if candidate.exists() else Path(sys.executable)


def build_plist(program: Path) -> str:
    args = [str(program)]
    if program.name != "konsent-app":  # fall back to `python -m konsent.app`
        args += ["-m", "konsent.app"]
    argv = "\n".join(f"        <string>{a}</string>" for a in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{argv}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>{LOG_DIR / 'konsent.log'}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR / 'konsent.log'}</string>
</dict>
</plist>
"""


def is_enabled() -> bool:
    return PLIST_PATH.exists()


def enable() -> Path:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(build_plist(executable()))
    # Ignore failures: the plist alone is enough to start at next login.
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{_uid()}", str(PLIST_PATH)],
        capture_output=True,
    )
    return PLIST_PATH


def disable() -> None:
    subprocess.run(
        ["launchctl", "bootout", f"gui/{_uid()}/{LABEL}"], capture_output=True
    )
    PLIST_PATH.unlink(missing_ok=True)


def _uid() -> int:
    import os

    return os.getuid()
