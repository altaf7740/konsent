from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .calibrate import calibrate
from .config import Config
from .pipeline import list_cameras, run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="konsent",
        description="A virtual camera that stays blurred until you lean in.",
    )
    p.add_argument("--config", type=Path, default=Path("config.toml"))
    p.add_argument("--camera", type=int, help="camera index")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--fps", type=int)
    p.add_argument("--mirror", action="store_true", help="flip the output horizontally")
    p.add_argument(
        "--preview",
        action="store_true",
        help="show a window instead of publishing a virtual camera",
    )
    p.add_argument("--hud", action="store_true", help="overlay live threshold readouts")
    p.add_argument("--list-cameras", action="store_true")
    p.add_argument(
        "--calibrate",
        action="store_true",
        help="measure your neutral head pose and save it to the config",
    )
    args = p.parse_args(argv)

    if args.list_cameras:
        found = list_cameras()
        print("cameras:", ", ".join(map(str, found)) if found else "none found")
        return 0

    cfg = Config.load(args.config)
    for name, value in (
        ("camera_index", args.camera),
        ("width", args.width),
        ("height", args.height),
        ("fps", args.fps),
    ):
        if value is not None:
            setattr(cfg, name, value)
    if args.mirror:
        cfg.mirror = True

    try:
        if args.calibrate:
            return calibrate(cfg, args.config)
        return run(cfg, preview=args.preview, hud=args.hud)
    except RuntimeError as exc:
        print(f"[konsent] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
