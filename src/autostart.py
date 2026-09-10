"""Start konsent's tray app at login, on macOS, Linux and Windows."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LABEL = "com.konsent.menubar"
NAME = "konsent"

# macOS
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs"
# Linux (XDG autostart — honoured by GNOME, KDE, XFCE and others)
DESKTOP_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "autostart"
    / f"{NAME}.desktop"
)
# Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> list[str]:
    """How to start the tray app without depending on PATH.

    Prefers the installed console script; falls back to the interpreter. On
    Windows we use pythonw.exe so no console window flashes up at login.
    """
    bindir = Path(sys.executable).parent
    if os.name == "nt":
        pythonw = bindir / "pythonw.exe"
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        return [str(exe), "-m", "konsent.app"]
    script = bindir / "konsent-app"
    if script.exists():
        return [str(script)]
    return [str(sys.executable), "-m", "konsent.app"]


# --- macOS ------------------------------------------------------------------


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


def executable() -> Path:
    candidate = Path(sys.executable).parent / "konsent-app"
    return candidate if candidate.exists() else Path(sys.executable)


# --- Linux ------------------------------------------------------------------


def build_desktop_entry(command: list[str]) -> str:
    exec_line = " ".join(f'"{c}"' if " " in c else c for c in command)
    return f"""[Desktop Entry]
Type=Application
Name=konsent
Comment=Blur the camera until you lean in
Exec={exec_line}
Terminal=false
X-GNOME-Autostart-enabled=true
"""


# --- dispatch ---------------------------------------------------------------


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return PLIST_PATH.exists()
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, NAME)
            return True
        except OSError:
            return False
    return DESKTOP_PATH.exists()


def enable() -> Path | str:
    if sys.platform == "darwin":
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_text(build_plist(executable()))
        # Ignore failure: the plist alone is enough for the next login.
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST_PATH)],
            capture_output=True,
        )
        return PLIST_PATH
    if os.name == "nt":
        import winreg

        command = subprocess.list2cmdline(launch_command())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command)
        return f"HKCU\\{RUN_KEY}\\{NAME}"
    DESKTOP_PATH.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_PATH.write_text(build_desktop_entry(launch_command()))
    return DESKTOP_PATH


def disable() -> None:
    if sys.platform == "darwin":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True
        )
        PLIST_PATH.unlink(missing_ok=True)
        return
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, NAME)
        except OSError:
            pass
        return
    DESKTOP_PATH.unlink(missing_ok=True)
