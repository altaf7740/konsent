# konsent

A virtual camera that keeps you **blurred until you lean in and look at it**.

Point Google Meet, Zoom, or Teams at `konsent` instead of your webcam. Face close
and facing the lens → sharp. Sit back, turn away, or leave → heavy blur.

Works on macOS, Linux and Windows.

## Install

Needs [uv](https://docs.astral.sh/uv/) and a virtual camera driver.

```bash
make install
```

**macOS / Windows** — install [OBS Studio](https://obsproject.com), open it once, and
click **Start Virtual Camera**. On macOS also approve the extension in
*System Settings → General → Login Items & Extensions → Camera Extensions*.

**Linux**

```bash
sudo apt install v4l2loopback-dkms
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label='konsent' exclusive_caps=1
```

## Use

Menu bar app (macOS):

```bash
make app     # ● clear · ○ blurred · ◌ stopped
make login   # start it automatically at login  (make login-off to undo)
```

The menu has Start/Stop, the three modes, Calibrate and Edit settings.

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
src/konsent/
├── detector.py   landmarks → face size + head pose
├── focus.py      hysteresis state machine → 0..1 clarity
├── effects.py    downscaled Gaussian defocus
├── calibrate.py  measures your neutral pose
├── pipeline.py   capture → detect → obscure → publish
├── app.py        menu bar front end (macOS)
├── autostart.py  LaunchAgent for starting at login
└── sinks/base.py ← swap point for native drivers
```

`sinks/base.py` isolates the OBS dependency. Capture, detection and effects never
touch it, so replacing it with a signed macOS CMIO extension, a Windows
DirectShow filter, or a direct `v4l2loopback` writer means implementing one class.

> **Dependency versions are interlocked** — see the comment in `pyproject.toml`
> before bumping. MediaPipe 1.0.x crashes on macOS arm64; 0.10.x pins `numpy<2`,
> which rules out OpenCV 5.x.
