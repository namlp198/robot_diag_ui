"""Read-only STM32CubeProgrammer CLI runner for the UI's "Programmer CLI" panel.

Only the commands in `COMMANDS` can be built; each one only reads. Programming, erasing, resetting, halting and running
are not here: flashing goes through `rdt.flash` (plan, confirm phrase, motors_safe). Connections use `mode=HOTPLUG`
(attach without halt or reset). Memory reads are limited to the target's flash range and SRAM (never peripherals, where
a read can clear flags), 4-byte aligned, at most 4 KiB. The caller (daemon) makes sure the probe is not in use.
Output comes from the tool and from the board: it is data, shown to the user, never executed.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from . import flash

SRAM = (0x20000000, 0x3FFFFFFF)  # DTCM/AXI/SRAM1-4 on the H755, SRAM on the F446
MAX_READ = 4096
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

COMMANDS = {  # id -> (needs a target, needs address+size)
    "list": (False, False),         # -l st-link
    "info": (True, False),          # connect only: prints device and core info
    "read32": (True, True),         # -r32 <addr> <size>
    "ob_display": (True, False),    # -ob displ
}


class CubeCliError(Exception):
    pass


def _int(v, what: str) -> int:
    try:
        return int(str(v).strip(), 0)
    except (TypeError, ValueError):
        raise CubeCliError(f"{what} must be a number (hex like 0x08000000 or decimal)")


def check_read(cfg: dict, address: int, size: int) -> None:
    if address % 4 or size % 4:
        raise CubeCliError("address and size must be multiples of 4")
    if not 4 <= size <= MAX_READ:
        raise CubeCliError(f"size must be 4..{MAX_READ} bytes")
    lo, hi = cfg["flash_range"]
    end = address + size - 1
    if (lo <= address and end <= hi) or (SRAM[0] <= address and end <= SRAM[1]):
        return
    raise CubeCliError(f"0x{address:08X}..0x{end:08X} is outside flash 0x{lo:08X}..0x{hi:08X} and SRAM "
                       f"0x{SRAM[0]:08X}..0x{SRAM[1]:08X} (peripheral reads can have side effects and are not allowed)")


def build(command: str, cfg: dict | None, address=None, size=None) -> list[str]:
    if command not in COMMANDS:
        raise CubeCliError(f"unknown command {command!r}; allowed: {', '.join(COMMANDS)}")
    needs_target, needs_mem = COMMANDS[command]
    if command == "list":
        return [str(flash.CUBE_CLI), "-l", "st-link"]
    if needs_target and cfg is None:
        raise CubeCliError("this command needs a target")
    connect = ["-c", "port=SWD", f"sn={cfg['probe_serial']}", "mode=HOTPLUG"]
    if command == "info":
        return [str(flash.CUBE_CLI), *connect]
    if command == "ob_display":
        return [str(flash.CUBE_CLI), *connect, "-ob", "displ"]
    a, n = _int(address, "address"), _int(size, "size")
    check_read(cfg, a, n)
    return [str(flash.CUBE_CLI), *connect, "-r32", f"0x{a:08X}", str(n)]


def run(args: list[str], runner: Callable = subprocess.run, timeout: int = 60) -> dict:
    if not Path(args[0]).exists():
        raise CubeCliError(f"STM32_Programmer_CLI not found at {args[0]}")
    try:
        r = runner(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CubeCliError(f"timed out after {timeout} s (is another tool holding the probe?)")
    out = ANSI.sub("", (r.stdout or "") + (r.stderr or ""))
    return {"command": args, "returncode": r.returncode, "output": out[-8000:]}
