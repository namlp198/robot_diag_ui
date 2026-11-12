"""Where things live, for a source checkout and for the installed (PyInstaller) app.

* source checkout: everything is under the repository root (targets.yaml, sessions/, ui/dist).
* installed app (`sys.frozen`): read-only resources (the built UI, the default targets.yaml) are inside the bundle; everything the user
  changes (targets.yaml, sessions/, settings, flash log) goes to %LOCALAPPDATA%\\RobotDiag so the install folder can stay read-only and
  an uninstall or an upgrade never deletes recordings.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_NAME = "RobotDiag"

if FROZEN:
    RESOURCES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
else:
    RESOURCES = Path(__file__).resolve().parents[1]
    DATA = RESOURCES

UI_DIST = RESOURCES / "ui" / "dist"
LOG_DIR = DATA / "logs"


def ensure_data() -> Path:
    """Create the data folder and, in the installed app, seed targets.yaml from the bundled default on first run."""
    DATA.mkdir(parents=True, exist_ok=True)
    seed = RESOURCES / "targets.yaml"
    target = DATA / "targets.yaml"
    if FROZEN and not target.exists() and seed.exists():
        shutil.copyfile(seed, target)
    return DATA
