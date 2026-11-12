"""Check that the firmware running on a board is the one the ELF was built from (read-only flash reads).

Variable addresses and layouts come from the ELF; if the board runs another build, every value read is
wrong without any error. So the daemon samples a few flash chunks and compares them with the ELF image.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from elftools.elf.elffile import ELFFile

FLASH_LO, FLASH_HI = 0x08000000, 0x09000000


@dataclass
class VerifyResult:
    checked: int = 0
    mismatched: list[int] = field(default_factory=list)  # chunk addresses that differ
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.checked > 0 and not self.mismatched

    def summary(self) -> str:
        if self.error:
            return f"not verified: {self.error}"
        if self.checked == 0:
            return "not verified: ELF has no flash image"
        if self.mismatched:
            return (f"FIRMWARE MISMATCH: {len(self.mismatched)}/{self.checked} flash chunks differ from the ELF "
                    f"(first at 0x{self.mismatched[0]:08X}); values read with this ELF are not trustworthy")
        return f"firmware matches ELF ({self.checked} flash chunks)"


def flash_image(elf_path: Path) -> list[tuple[int, bytes]]:
    """Loadable flash sections as (address, bytes), ascending."""
    out = []
    with open(elf_path, "rb") as fh:
        elf = ELFFile(fh)
        for sec in elf.iter_sections():
            fl = sec["sh_flags"]
            if sec["sh_type"] != "SHT_PROGBITS" or not fl & 0x2:  # SHF_ALLOC
                continue
            addr = sec["sh_addr"]
            if FLASH_LO <= addr < FLASH_HI and sec["sh_size"]:
                out.append((addr, sec.data()))
    return sorted(out)


def chunk_plan(image: list[tuple[int, bytes]], chunks: int = 16, size: int = 64) -> list[tuple[int, bytes]]:
    """Evenly spaced chunks across the image; the first one is the start of the first section (vector table)."""
    flat = [(a, d) for a, d in image if len(d) >= size]
    if not flat:
        return []
    total = sum(len(d) for _, d in flat)
    picks = []
    for i in range(chunks):
        off = (total - size) * i // max(chunks - 1, 1)
        for a, d in flat:
            if off < len(d):
                off = min(off, len(d) - size)
                picks.append((a + off, d[off:off + size]))
                break
            off -= len(d)
    return picks


def verify(read: Callable[[int, int], bytes], elf_path: Path, chunks: int = 16, size: int = 64,
           image: list[tuple[int, bytes]] | None = None) -> VerifyResult:
    """Compare flash chunks with the ELF, or with `image` (blocks from rdt.firmware.load_image: .hex or .bin files)."""
    res = VerifyResult()
    try:
        plan = chunk_plan(image if image is not None else flash_image(elf_path), chunks, size)
        for addr, expect in plan:
            res.checked += 1
            if read(addr, len(expect)) != expect:
                res.mismatched.append(addr)
    except Exception as e:  # unreadable flash/ELF is "not verified", never "verified"
        res.error = str(e)
    return res
