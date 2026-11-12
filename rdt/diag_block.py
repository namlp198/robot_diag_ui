"""Decoder for `diag_block_t` v1 (DRAFT, see outputs/claude_drafts/diag_block_spec.md).

One read of the block (~96 B) replaces many variable reads and survives renames of internal firmware variables.
The firmware side does not exist yet: nothing here talks to a board until a firmware repo adopts the spec.
Torn reads: the firmware writes `seq` odd before updating and even after (seqlock); `read_consistent` reads twice.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Callable

MAGIC = 0x47414944  # 'DIAG' little endian bytes 44 49 41 47
VERSION = 1
# magic u32, version u16, size u16, product u8, fw[3], seq u32, uptime_ms u32, reset_cause u32, reset_count u32,
# rx_bytes frames_ok crc_err truncated lost dup err_link_id tx_frames tx_fail (9 x u32), last_rx_age_ms u32,
# flags u16, link_quality u8, pad u8, heap_free u32, heap_min u32, stack_min_words 8 x u16, fdcan_psr u32, fdcan_ecr u32,
# crc32 u32 (over all previous bytes)
_FMT = "<IHHB3sIIII" + "I" * 9 + "I" + "HBB" + "II" + "H" * 8 + "II" + "I"
SIZE = struct.calcsize(_FMT)
FIELDS = ["magic", "version", "size", "product", "fw", "seq", "uptime_ms", "reset_cause", "reset_count",
          "rx_bytes", "frames_ok", "crc_err", "truncated", "lost", "dup", "err_link_id", "tx_frames", "tx_fail",
          "last_rx_age_ms", "flags", "link_quality", "pad", "heap_free", "heap_min",
          *[f"stack_min_words_{i}" for i in range(8)], "fdcan_psr", "fdcan_ecr", "crc32"]
FLAG_BITS = {0: "connected", 1: "failsafe", 2: "estop", 3: "armed", 4: "input_valid", 5: "can_bus_off"}


class DiagBlockError(Exception):
    pass


@dataclass(frozen=True)
class DiagBlock:
    values: dict

    def __getitem__(self, k):
        return self.values[k]

    @property
    def flags(self) -> list[str]:
        f = self.values["flags"]
        return [n for b, n in FLAG_BITS.items() if f >> b & 1]

    @property
    def stack_min_words(self) -> list[int]:
        return [self.values[f"stack_min_words_{i}"] for i in range(8)]


def decode(raw: bytes) -> DiagBlock:
    if len(raw) < SIZE:
        raise DiagBlockError(f"need {SIZE} bytes, got {len(raw)}")
    raw = raw[:SIZE]
    v = dict(zip(FIELDS, struct.unpack(_FMT, raw)))
    if v["magic"] != MAGIC:
        raise DiagBlockError(f"bad magic 0x{v['magic']:08X} (not a diag block, or firmware without it)")
    if v["version"] != VERSION:
        raise DiagBlockError(f"unsupported version {v['version']} (this decoder knows {VERSION})")
    if v["size"] != SIZE:
        raise DiagBlockError(f"size field {v['size']} != {SIZE}")
    if v["seq"] & 1:
        raise DiagBlockError("seq is odd: block was being written")
    if zlib.crc32(raw[:-4]) & 0xFFFFFFFF != v["crc32"]:
        raise DiagBlockError("crc32 mismatch")
    v["fw"] = ".".join(str(b) for b in v["fw"])
    return DiagBlock(v)


def encode(values: dict) -> bytes:
    """Test helper and reference for the firmware: build a valid block from field values."""
    d = {k: 0 for k in FIELDS}
    d.update(values)
    d.update(magic=MAGIC, version=VERSION, size=SIZE)
    if isinstance(d["fw"], str):
        d["fw"] = bytes(int(x) for x in d["fw"].split("."))
    elif d["fw"] == 0:
        d["fw"] = b"\0\0\0"
    body = struct.pack(_FMT[:-1], *[d[k] for k in FIELDS[:-1]])
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def read_consistent(read: Callable[[int, int], bytes], address: int, tries: int = 3) -> DiagBlock:
    """Read, decode, read again: both must be valid and have the same seq."""
    last = None
    for _ in range(tries):
        try:
            a, b = decode(read(address, SIZE)), decode(read(address, SIZE))
        except DiagBlockError as e:
            last = e
            continue
        if a["seq"] == b["seq"]:
            return b
        last = DiagBlockError("seq changed between reads")
    raise last or DiagBlockError("unreadable")
