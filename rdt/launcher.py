"""Entry point of the installed app (RobotDiag.exe): the native window by default, the CLI when arguments are given.

The exe is a windowed program (no console), so stdout and stderr go to a log file under %LOCALAPPDATA%\\RobotDiag\\logs.
`RobotDiag.exe` -> `rdt app`; `RobotDiag.exe serve --port 8899`, `RobotDiag.exe resolve ...` work like the `rdt` command.
"""
from __future__ import annotations

import sys

from . import paths


def _log_to_file():
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    f = open(paths.LOG_DIR / "robot_diag.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


def main() -> int:
    paths.ensure_data()
    if paths.FROZEN:
        _log_to_file()
    from .cli import main as cli_main
    return cli_main(sys.argv[1:] or ["app"])


if __name__ == "__main__":
    raise SystemExit(main())
