# konsent

A virtual camera that keeps you **blurred until you lean in and look at it**.

Point Google Meet, Zoom, or Teams at `konsent` instead of your webcam. Face close
and facing the lens → sharp. Sit back, turn away, or leave → heavy blur.

Works on macOS, Linux and Windows — though only macOS has been tested on real
hardware. See [Platform support](#platform-support).

## Install

Needs [uv](https://docs.astral.sh/uv/).

```bash
make install
```

That installs the Python packages, downloads the face model, then detects your OS
and offers to install the virtual camera driver — OBS via Homebrew on macOS or
winget on Windows, `v4l2loopback` via apt/dnf/pacman/zypper on Linux. It asks
before running anything that needs `sudo`, and prints the exact command first.
Use `make check` to see what is missing without changing anything.

One step it cannot do for you: on macOS, approving the camera extension in
*System Settings → General → Login Items & Extensions → Camera Extensions*.
macOS requires a human for that. `make check` tells you when it is pending.

## Virtual camera setup

konsent has to publish its blurred feed as a camera device that other apps can
select. Every OS does that differently, and `make install` handles most of it —
this section is what to do when it doesn't, and how to verify each step.

`make check` reports the state of all of this at any time.

<details open>
<summary><b>macOS</b></summary>

The driver is a **Core Media I/O system extension**, and konsent borrows the one
OBS ships. That is deliberate: macOS refuses to load an unsigned camera
extension, and signing your own needs a paid Apple Developer account. OBS's is
already signed and notarised, so you get a system-wide camera for free.

```bash
brew install --cask obs          # or: make install
open -a OBS                      # then click "Start Virtual Camera"
```

Clicking **Start Virtual Camera** once is what registers the extension with
macOS. You then have to approve it — macOS blocks camera extensions from being
enabled by software, so nothing can do this step for you:

**System Settings → General → Login Items & Extensions → Camera Extensions → enable OBS**

That row is easy to miss: it sits at the bottom of a long page, under a small
*Extensions* heading. Typing `camera extensions` into the System Settings search
box jumps straight to it.

Verify:

```bash
systemextensionsctl list | grep obs
#   ... [activated enabled]        <- ready
#   ... [activated waiting for user]  <- still needs the toggle above

system_profiler SPCameraDataType | grep "OBS Virtual Camera"
```

Once enabled, quit and reopen OBS. You do not need OBS running afterwards — only
its extension. Some macOS versions want a reboot before the device appears.

</details>

<details open>
<summary><b>Ubuntu / Linux</b></summary>

The driver is **v4l2loopback**, a kernel module that creates a virtual
`/dev/video*` device. It is a DKMS module, so it compiles against your running
kernel and needs matching headers.

```bash
sudo apt install v4l2loopback-dkms linux-headers-$(uname -r)

sudo modprobe v4l2loopback devices=1 video_nr=10 \
     card_label=konsent exclusive_caps=1
```

Both options matter. **`exclusive_caps=1` is required** — without it Chrome and
Firefox enumerate the device but refuse to use it, which looks like konsent is
broken when it isn't. `card_label=konsent` is what the device is called in the
camera picker; without it you get a generic "Dummy video device".

Make it survive a reboot:

```bash
echo v4l2loopback | sudo tee /etc/modules-load.d/konsent.conf
echo 'options v4l2loopback devices=1 video_nr=10 card_label=konsent exclusive_caps=1' \
  | sudo tee /etc/modprobe.d/konsent.conf
```

Verify:

```bash
lsmod | grep v4l2loopback         # module loaded
ls -l /dev/video10                # device exists
v4l2-ctl --list-devices           # shows "konsent"  (sudo apt install v4l-utils)
```

Two things that bite on Linux:

- **Secure Boot** rejects unsigned kernel modules. If `modprobe` fails with
  *"Key was rejected by service"*, either enrol a MOK key for DKMS or disable
  Secure Boot.
- **Wayland** restricts global key capture, so the terminal hotkeys likely won't
  fire. The tray menu does the same job. Check with `echo $XDG_SESSION_TYPE`.

</details>

<details open>
<summary><b>Windows</b></summary>

The driver is the **DirectShow filter** that OBS registers when it installs, so
the setup is the same shape as macOS but without an approval step.

```powershell
winget install -e --id OBSProject.OBSStudio    # or: make install
```

Open OBS once and click **Start Virtual Camera** in the Controls panel to
register the filter. OBS registers both 32- and 64-bit filters, so older apps
that load the 32-bit one still see the device.

Verify by opening the built-in **Camera** app and switching cameras — *OBS
Virtual Camera* should be in the list. Or run `make cameras`.

If the device never appears, run the OBS installer again and choose **Repair**;
filter registration needs administrator rights and is skipped if the installer
was run without them.

</details>

### Selecting it in your meeting app

Start konsent (`make app` or `make run`), then pick the device:

| App | Where |
|---|---|
| Google Meet | Settings (⚙) → Video → Camera |
| Zoom | Settings → Video → Camera |
| Teams | Settings → Devices → Camera |
| Slack, Discord, FaceTime | Settings → Video / Camera |

The device is called **OBS Virtual Camera** on macOS and Windows, and **konsent**
on Linux (that's the `card_label`).

Two habits worth knowing:

- **Start konsent before the meeting app.** Browsers and Electron apps enumerate
  cameras once at launch and cache the list. If the device isn't there yet, quit
  the app fully — including background Teams and Slack — and reopen it.
- **A frozen or black feed** usually means konsent stopped. Check the tray icon:
  ◌ means it isn't running.


## Use

Tray app — menu bar on macOS, system tray on Linux and Windows:

```bash
make app     # ● clear · ○ blurred · ◌ stopped
make login   # start it automatically at login  (make login-off to undo)
```

The menu has Start/Stop, the three modes, Calibrate and Edit settings.
`make login` installs a LaunchAgent on macOS, an XDG autostart entry on Linux,
and an HKCU Run key on Windows.

Or from the terminal, anywhere:

```bash
make calibrate   # once per camera setup — sit normally, look at the lens, 4s
make run         # then pick "OBS Virtual Camera" in Meet
```

Calibration is not optional. Absolute head pose depends on where your camera
physically sits — a laptop lid is below eye level, so a straight-on face measures
~24° of pitch and would never clear the threshold.

| Command | |
|---|---|
| `make app` | Menu bar app (macOS) |
| `make login` / `make login-off` | Start at login, on/off |
| `make run` | Start the virtual camera in the terminal |
| `make tune` | Preview window with live threshold readouts |
| `make check` | Report what is missing, install nothing |
| `make test` | Run the test suite |
| `make cameras` | List available cameras |
| `make clean` | Remove venv, caches and the downloaded model |

In terminal mode, <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd> forces clear and <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>B</kbd> forces blur; press
again for automatic. These need Accessibility permission on macOS, and everything
else still works without it. The menu bar app uses its menu instead — pynput's
listener calls Text Input Source APIs off the main queue, which trips an AppKit
assertion under a run loop.

## Tuning

Run `make tune` and watch each live value against the threshold in effect, then
edit `config.toml` (copy `config.toml.example`).

| Symptom | Fix |
|---|---|
| Have to lean in too far | Lower `face_ratio_enter` |
| Blurs when you shift slightly | Lower `face_ratio_exit`, raise `grace_seconds` |
| Stays clear when you sit back | Raise `face_ratio_exit` |
| Blurs when you glance at notes | Raise `yaw_exit` / `pitch_exit` |
| Transition feels abrupt | Raise `fade_seconds` |
| Not blurred enough | Raise `blur_strength` |

## How it works

```
webcam → capture → MediaPipe landmarks → focus decision → blur → virtual camera → Meet
                                               │
                          face size + head pose + hysteresis + hotkey override
```

Two thresholds, not one: becoming clear needs a larger, straighter-on face than
staying clear does, so hovering at the boundary doesn't flicker. A grace period
rides out dropped detections, and transitions crossfade.

```
src/                 # installs as the `konsent` package
├── detector.py   landmarks → face size + head pose
├── focus.py      hysteresis state machine → 0..1 clarity
├── effects.py    downscaled Gaussian defocus
├── calibrate.py  measures your neutral pose
├── pipeline.py   capture → detect → obscure → publish
├── controller.py capture thread + state, shared by every front end
├── tray/         menu bar (rumps) on macOS, system tray (pystray) elsewhere
├── autostart.py  LaunchAgent / XDG autostart / Run key
└── sinks/base.py ← swap point for native drivers
```

`sinks/base.py` isolates the OBS dependency. Capture, detection and effects never
touch it, so replacing it with a signed macOS CMIO extension, a Windows
DirectShow filter, or a direct `v4l2loopback` writer means implementing one class.

> **Dependency versions are interlocked** — see the comment in `pyproject.toml`
> before bumping. MediaPipe 1.0.x crashes on macOS arm64; 0.10.x pins `numpy<2`,
> which rules out OpenCV 5.x.

## Platform support

Everything is written cross-platform, but only macOS has been run end to end.

| | macOS | Linux | Windows |
|---|---|---|---|
| Detection, blur, focus logic | tested | portable | portable |
| Camera capture | tested | untested | untested |
| Virtual camera | tested | untested | untested |
| Tray app | tested | untested | untested |
| Start at login | tested | untested | untested |
| Global hotkeys | disabled¹ | untested² | untested |

¹ pynput's macOS backend calls Text Input Source APIs off the main queue, which
trips a dispatch assertion under an AppKit run loop. The tray menu replaces them.
² Likely needs X11; Wayland restricts global key capture.

"Portable" means written for it with no known blocker — not verified. macOS alone
produced three surprises (a MediaPipe Metal crash, `CAP_AVFOUNDATION` opening the
camera but reading nothing, and the pynput assertion), so expect the other two to
have their own.
