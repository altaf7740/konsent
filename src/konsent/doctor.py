"""Detect what konsent needs on this OS, and offer to install it.

`make install` runs this after `uv sync`: Python packages are only half the
setup, since the virtual camera needs a system driver on every platform.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

OK, BAD, WARN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: list[str] | None = None       # a command we can offer to run
    manual: str = ""                   # steps only the user can do
    warn_only: bool = False
    env: dict[str, str] = field(default_factory=dict)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    except FileNotFoundError:
        return 127, ""


# --- shared checks ----------------------------------------------------------


def check_model() -> Check:
    from .detector import MODEL_PATH, ensure_model

    if MODEL_PATH.exists():
        return Check("Face model", True, str(MODEL_PATH))
    try:
        path = ensure_model()
        return Check("Face model", True, f"downloaded to {path}")
    except Exception as exc:
        return Check("Face model", False, f"download failed: {exc}")


def check_camera() -> Check:
    import cv2

    cap = cv2.VideoCapture(0)
    ok = cap.isOpened() and cap.read()[0]
    cap.release()
    if ok:
        return Check("Camera", True, "camera 0 opens and delivers frames")
    if _konsent_is_running():
        return Check(
            "Camera",
            True,
            "in use by konsent itself — that's expected",
        )
    return Check(
        "Camera",
        False,
        "camera 0 gave no frames",
        manual="Grant camera access to your terminal, close other apps using the "
        "camera, or try `make cameras` to find another index.",
        warn_only=True,
    )


def _konsent_is_running() -> bool:
    if os.name == "nt":
        code, out = _run(["tasklist"])
        return code == 0 and "konsent" in out.lower()
    return _run(["pgrep", "-f", "konsent-app"])[0] == 0


# --- macOS ------------------------------------------------------------------


def _macos_checks() -> list[Check]:
    checks: list[Check] = []
    obs = os.path.exists("/Applications/OBS.app")
    checks.append(
        Check(
            "OBS Studio",
            obs,
            "/Applications/OBS.app" if obs else "not installed",
            fix=["brew", "install", "--cask", "obs"] if not obs and shutil.which("brew") else None,
            manual="" if shutil.which("brew") else "Download it from https://obsproject.com",
        )
    )

    _, out = _run(["systemextensionsctl", "list"])
    enabled = "obs-studio.mac-camera-extension" in out and "activated enabled" in out
    pending = "activated waiting for user" in out
    checks.append(
        Check(
            "Camera extension",
            enabled,
            "enabled" if enabled else ("waiting for your approval" if pending else "not registered"),
            manual=(
                "Approve it in System Settings > General > Login Items & Extensions "
                "> Camera Extensions (search 'camera extensions')."
                if pending
                else "Open OBS once and click 'Start Virtual Camera' to register it."
            )
            if not enabled
            else "",
        )
    )

    _, out = _run(["system_profiler", "SPCameraDataType"])
    present = "OBS Virtual Camera" in out
    checks.append(
        Check(
            "Virtual camera",
            present,
            "OBS Virtual Camera is available" if present else "device not found",
            manual="" if present else "It appears once the camera extension is approved.",
        )
    )
    return checks


# --- Linux ------------------------------------------------------------------

_LINUX_PACKAGES = {
    "apt": ["sudo", "apt", "install", "-y", "v4l2loopback-dkms"],
    "dnf": ["sudo", "dnf", "install", "-y", "v4l2loopback"],
    "pacman": ["sudo", "pacman", "-S", "--noconfirm", "v4l2loopback-dkms"],
    "zypper": ["sudo", "zypper", "install", "-y", "v4l2loopback-kmp-default"],
}

_MODPROBE = [
    "sudo", "modprobe", "v4l2loopback",
    "devices=1", "video_nr=10", "card_label=konsent", "exclusive_caps=1",
]

_PERSIST = (
    "echo v4l2loopback | sudo tee /etc/modules-load.d/konsent.conf >/dev/null && "
    "echo 'options v4l2loopback devices=1 video_nr=10 card_label=konsent "
    "exclusive_caps=1' | sudo tee /etc/modprobe.d/konsent.conf >/dev/null"
)


def _linux_checks() -> list[Check]:
    checks: list[Check] = []
    manager = next((m for m in _LINUX_PACKAGES if shutil.which(m)), None)

    installed = os.path.exists("/sys/module/v4l2loopback") or _run(["modinfo", "v4l2loopback"])[0] == 0
    checks.append(
        Check(
            "v4l2loopback module",
            installed,
            "installed" if installed else "not installed",
            fix=_LINUX_PACKAGES.get(manager) if not installed and manager else None,
            manual="" if manager else "Install the v4l2loopback package for your distro.",
        )
    )

    loaded = os.path.exists("/sys/module/v4l2loopback")
    checks.append(
        Check(
            "v4l2loopback loaded",
            loaded,
            "loaded" if loaded else "not loaded",
            fix=None if loaded else _MODPROBE,
        )
    )

    persisted = os.path.exists("/etc/modules-load.d/konsent.conf")
    checks.append(
        Check(
            "Loads at boot",
            persisted,
            "configured" if persisted else "not configured",
            fix=None if persisted else ["sh", "-c", _PERSIST],
            warn_only=True,
        )
    )

    session = os.environ.get("XDG_SESSION_TYPE", "")
    checks.append(
        Check(
            "Global hotkeys",
            session != "wayland",
            f"session type: {session or 'unknown'}",
            manual="Wayland restricts global key capture; use the tray menu instead."
            if session == "wayland"
            else "",
            warn_only=True,
        )
    )
    return checks


# --- Windows ----------------------------------------------------------------


def _windows_checks() -> list[Check]:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\obs-studio"),
        os.path.expandvars(r"%ProgramFiles(x86)%\obs-studio"),
    ]
    obs = any(os.path.exists(p) for p in candidates)
    return [
        Check(
            "OBS Studio",
            obs,
            "installed" if obs else "not installed",
            fix=["winget", "install", "-e", "--id", "OBSProject.OBSStudio"]
            if not obs and shutil.which("winget")
            else None,
            manual="" if shutil.which("winget") else "Download it from https://obsproject.com",
        ),
        Check(
            "Virtual camera",
            obs,
            "registered with OBS" if obs else "needs OBS",
            manual="" if obs else "Open OBS once and click 'Start Virtual Camera'.",
        ),
    ]


# --- driver -----------------------------------------------------------------


def collect() -> list[Check]:
    system = platform.system()
    by_os = {"Darwin": _macos_checks, "Linux": _linux_checks, "Windows": _windows_checks}
    checks = [check_model(), check_camera()]
    checks += by_os.get(system, lambda: [])()
    return checks


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    return input(f"    {question} [y/N] ").strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="konsent-setup",
        description="Check and install what konsent needs on this machine.",
    )
    ap.add_argument("--check", action="store_true", help="report only, never install")
    ap.add_argument("--yes", action="store_true", help="run fixes without asking")
    args = ap.parse_args(argv)

    print(f"\nkonsent setup — {platform.system()} {platform.machine()}\n")
    checks = collect()
    fixed_any = False

    for check in checks:
        mark = OK if check.ok else (WARN if check.warn_only else BAD)
        print(f"  {mark} {check.name:20s} {check.detail}")
        if check.ok:
            continue
        if check.fix and not args.check:
            printable = " ".join(check.fix)
            print(f"    would run: {printable}")
            if _confirm("run it?", args.yes):
                if subprocess.run(check.fix).returncode == 0:
                    fixed_any = True
                else:
                    print("    command failed; see the output above")
        if check.manual:
            print(f"    → {check.manual}")

    if fixed_any:
        print("\nSome things changed — re-run `make install` to confirm.")

    blocking = [c for c in checks if not c.ok and not c.warn_only]
    if blocking:
        print(f"\n{len(blocking)} thing(s) still need attention before konsent will run.\n")
        return 1
    print("\nReady. Run `make calibrate`, then `make app`.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
