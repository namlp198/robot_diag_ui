"""Firmware files the user registered in Settings: ELF (symbols or image), Intel HEX and raw BIN. Pure Python, no hardware.

`inspect` says what a file is without trusting its name; `load_image` returns the flash content as (address, bytes) blocks, which
is what the flash plan checks against the board's flash range and what is compared with the flash after programming.
A .bin has no address inside, so the caller must give it (the plan defaults to the start of the target's flash).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from elftools.elf.elffile import ELFFile

from .verify import FLASH_HI, FLASH_LO, flash_image

KINDS = {".elf": "elf", ".axf": "elf", ".out": "elf", ".hex": "hex", ".ihx": "hex", ".bin": "bin"}
MAX_BYTES = 64 * 1024 * 1024


class FirmwareError(Exception):
    pass


def kind_of(path: Path) -> str | None:
    return KINDS.get(Path(path).suffix.lower())


def parse_ihex(text: str) -> list[tuple[int, bytes]]:
    """Intel HEX records 00 data, 01 end, 02/04 segment/linear base, 05 start (ignored). Checksums are verified; adjacent bytes
    are merged into blocks. Raises FirmwareError on any malformed line."""
    blocks: list[tuple[int, bytearray]] = []
    base = 0
    ended = False
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if ended:
            raise FirmwareError(f"line {n}: data after the end-of-file record")
        if not line.startswith(":") or len(line) < 11:
            raise FirmwareError(f"line {n}: not an Intel HEX record")
        try:
            raw = bytes.fromhex(line[1:])
        except ValueError:
            raise FirmwareError(f"line {n}: not hexadecimal")
        ln, off, typ, data, chk = raw[0], int.from_bytes(raw[1:3], "big"), raw[3], raw[4:-1], raw[-1]
        if len(data) != ln or (sum(raw[:-1]) + chk) & 0xFF:
            raise FirmwareError(f"line {n}: length or checksum error")
        if typ == 0:
            addr = base + off
            if blocks and blocks[-1][0] + len(blocks[-1][1]) == addr:
                blocks[-1][1].extend(data)
            else:
                blocks.append((addr, bytearray(data)))
        elif typ == 1:
            ended = True
        elif typ == 2:
            base = int.from_bytes(data, "big") << 4
        elif typ == 4:
            base = int.from_bytes(data, "big") << 16
        elif typ not in (3, 5):
            raise FirmwareError(f"line {n}: unknown record type {typ}")
    if not ended:
        raise FirmwareError("no end-of-file record (truncated file?)")
    return [(a, bytes(b)) for a, b in blocks if b]


def load_image(path: Path, address: int | None = None) -> list[tuple[int, bytes]]:
    """Flash content of the file as (address, bytes) blocks, ascending."""
    path = Path(path)
    k = kind_of(path)
    if k is None:
        raise FirmwareError("file must be .elf, .hex or .bin")
    if path.stat().st_size > MAX_BYTES:
        raise FirmwareError("file is larger than 64 MiB")
    if k == "elf":
        return flash_image(path)
    if k == "hex":
        return sorted(parse_ihex(path.read_text(encoding="ascii", errors="strict")))
    if address is None:
        raise FirmwareError(".bin needs a start address")
    data = path.read_bytes()
    return [(address, data)] if data else []


def inspect(path: str | Path) -> dict:
    """What the file is, for the Settings list. Never raises: problems are reported in `error`."""
    p = Path(path)
    info: dict = {"path": str(p), "exists": p.is_file()}
    if not p.is_file():
        info["error"] = "file not found"
        return info
    st = p.stat()
    info.update(size=st.st_size, mtime=int(st.st_mtime), kind=kind_of(p), name=p.name)
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        info["sha8"] = h.hexdigest()[:8]
        if info["kind"] is None:
            info["error"] = "file must be .elf, .hex or .bin"
        elif info["kind"] == "elf":
            with open(p, "rb") as fh:
                e = ELFFile(fh)
                info["arm"] = e["e_machine"] == "EM_ARM" and e.elfclass == 32
                info["dwarf"] = e.has_dwarf_info()
                info["has_symtab"] = e.get_section_by_name(".symtab") is not None
            if not info["arm"]:
                info["error"] = "not a 32-bit ARM ELF"
            blocks = flash_image(p) if info["arm"] else []
            info["flash"] = [min(a for a, _ in blocks), max(a + len(d) for a, d in blocks) - 1] if blocks else None
        elif info["kind"] == "hex":
            blocks = parse_ihex(p.read_text(encoding="ascii", errors="strict"))
            info["flash"] = [min(a for a, _ in blocks), max(a + len(d) for a, d in blocks) - 1] if blocks else None
            if not blocks:
                info["error"] = "no data records"
        else:
            info["flash"] = None  # address comes from the user
    except (FirmwareError, OSError, ValueError, UnicodeError) as e:
        info["error"] = str(e)[:200]
    except Exception as e:  # a damaged ELF can raise anything from pyelftools
        info["error"] = f"unreadable: {str(e)[:120]}"
    return info


def in_flash(blocks: list[tuple[int, bytes]], lo: int, hi: int) -> bool:
    return bool(blocks) and all(lo <= a and a + len(d) - 1 <= hi for a, d in blocks)


__all__ = ["FirmwareError", "FLASH_LO", "FLASH_HI", "inspect", "load_image", "parse_ihex", "kind_of", "in_flash"]
