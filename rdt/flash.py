"""Gated flashing (D5). WRITES TO HARDWARE: `plan` is read-only, `run` is the only function that programs a board.

Gates, all required for `run`:
  1. the plan has no failed check (probe present, board DEV_ID equals the target's, ELF image inside the target's
     flash range, image path matches the target's `allowed_images`, image still has the hash that was planned);
  2. the caller typed the exact `confirm` phrase of this plan ("FLASH <target> <sha8>"), shown to the user by the UI;
  3. targets with `needs_motors_safe` (the robot) also need `motors_safe=True`: the user's statement that the wheels are off the ground
     and that they are at the robot and can cut its power at once (the robot's motor power comes with its supply, so power
     cannot be cut while flashing);
  4. the daemon is not sampling (the probe is needed exclusively; the caller stops it first).
Claude has no flash tool; its permission policy denies everything outside `mcp__rdt__*`, and none of those flashes.
After programming, the flash content is compared with the image (rdt.verify) and the result is appended to
`sessions/flash_log.jsonl`. Not implemented on purpose: .hex/.bin images, paired flashing, CM4.
Tests use a fake runner and probe reader; nothing here has been run against a real board.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from elftools.elf.elffile import ELFFile

from .verify import verify

CUBE_CLI = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe")
EM_ARM = 40


class FlashError(Exception):
    pass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class FlashPlan:
    target: str
    image: str
    sha256: str
    size_bytes: int
    segments: list[tuple[int, int]]
    checks: list[Check] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    confirm: str = ""
    needs_motors_safe: bool = False
    already_flashed: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def elf_segments(path: Path) -> list[tuple[int, int]]:
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        if elf["e_machine"] != "EM_ARM" or elf.elfclass != 32:
            raise FlashError("not a 32-bit ARM ELF")
        return [(s["p_paddr"], s["p_filesz"]) for s in elf.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_filesz"]]


def _glob_match(path: Path, pattern: Path) -> bool:
    """Segment-wise match: `*` never crosses a directory separator (fnmatch on the whole string would)."""
    a, b = path.parts, pattern.parts
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x.lower(), y.lower()) for x, y in zip(a, b))


def plan(target: str, cfg: dict, image: Path, base: Path, read: Callable[[int, int], bytes] | None,
         attached: Callable[[str], bool]) -> FlashPlan:
    """Read-only. `read` reads target memory (None if the probe cannot be opened); `attached(serial)` tells if the probe is listed."""
    image = Path(image).resolve()
    checks: list[Check] = []
    if image.suffix.lower() != ".elf" or not image.is_file():
        raise FlashError("image must be an existing .elf file (.hex/.bin are not supported)")
    p = FlashPlan(target, str(image), _sha256(image), image.stat().st_size, [], needs_motors_safe=bool(cfg.get("needs_motors_safe")))

    allowed = [Path(__import__("os").path.normpath(base / g)) for g in cfg.get("allowed_images", [])]  # `base`: the dir targets.yaml paths are relative to
    ok_img = any(_glob_match(image, g) for g in allowed)
    checks.append(Check("image_allowed_for_target", ok_img,
                        "matches targets.yaml allowed_images" if ok_img
                        else f"{image.name} is not in allowed_images for {target}: {cfg.get('allowed_images')}"))
    try:
        p.segments = elf_segments(image)
        lo, hi = cfg["flash_range"]
        bad = [(a, n) for a, n in p.segments if not (lo <= a and a + n - 1 <= hi)]
        checks.append(Check("image_inside_flash_range", not bad and bool(p.segments),
                            f"segments {[(hex(a), n) for a, n in p.segments]} within 0x{lo:08X}..0x{hi:08X}" if not bad
                            else f"segments outside the target's flash: {[(hex(a), n) for a, n in bad]}"))
    except FlashError as e:
        checks.append(Check("image_inside_flash_range", False, str(e)))

    checks.append(Check("probe_attached", attached(cfg["probe_serial"]), cfg["probe_serial"]))
    if read is None:
        checks.append(Check("board_dev_id", False, "cannot read the board (probe busy or not attached)"))
    else:
        try:
            dev = int.from_bytes(read(cfg["idcode_addr"], 4), "little") & 0xFFF
            checks.append(Check("board_dev_id", dev == cfg["dev_id"], f"read 0x{dev:03X}, expected 0x{cfg['dev_id']:03X} ({cfg.get('mcu')})"))
            if p.segments:
                p.already_flashed = verify(read, image).ok
        except Exception as e:  # fail closed: an unreadable board is a failed check
            checks.append(Check("board_dev_id", False, f"read failed: {e}"))
    p.checks = checks
    p.confirm = f"FLASH {target} {p.sha256[:8]}"
    p.command = [str(CUBE_CLI), "-c", "port=SWD", f"sn={cfg['probe_serial']}", "mode=NORMAL", "-w", str(image), "-v", "-rst"]
    return p


def run(p: FlashPlan, cfg: dict, confirm: str, motors_safe: bool, repo_root: Path, log_dir: Path,
        runner: Callable = subprocess.run,
        read_after: Callable[[], object] | None = None) -> dict:  # read_after: context manager with .read(addr, n)
    if not p.ok:
        raise FlashError("plan has failed checks: " + "; ".join(c.name for c in p.checks if not c.ok))
    if confirm != p.confirm:
        raise FlashError(f"confirmation phrase must be exactly: {p.confirm}")
    if p.needs_motors_safe and not motors_safe:
        raise FlashError(f"{p.target}: confirm the robot is safe (wheels off the ground, you are at the robot and can cut its power at once) before flashing")
    if _sha256(Path(p.image)) != p.sha256:
        raise FlashError("image changed after it was planned; plan again")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    r = runner(p.command, capture_output=True, text=True, timeout=300)
    out = ((r.stdout or "") + (r.stderr or ""))[-4000:]
    ok = r.returncode == 0
    verified = None
    if ok and read_after is not None:
        try:
            with read_after() as probe:  # a context manager (e.g. rdt.backend.Probe): must release the probe
                verified = verify(probe.read, Path(p.image)).ok
        except Exception:
            verified = False
    result = {"target": p.target, "image": p.image, "sha256": p.sha256, "started_utc": started,
              "returncode": r.returncode, "programmed": ok, "verified_after": verified, "output_tail": out}
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "flash_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=True) + "\n")
    return result
