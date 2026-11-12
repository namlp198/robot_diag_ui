"""ITM/SWO decoding for a future robot log source (spike S4). Pure Python, no hardware.

Only software-source ITM packets (stimulus ports) are decoded; sync, overflow, timestamp, DWT and extension packets are
skipped. Text written to a stimulus port (for example `ITM_SendChar` in firmware) is assembled into lines and cleaned with
the same rules as VCP text (`rdt.vcp.clean_line`): it is data from a board, never instructions.
"""
from __future__ import annotations

from dataclasses import dataclass

from .vcp import clean_line

SIZES = {1: 1, 2: 2, 3: 4}  # ITM source packet SS field -> payload bytes


@dataclass
class ItmPacket:
    port: int
    data: bytes


class ItmDecoder:
    """Feed bytes as they arrive (packets may be split across reads); `feed` returns the packets completed so far."""

    def __init__(self):
        self.buf = bytearray()
        self.overflows = 0
        self.skipped = 0
        self.zeros = 0  # run of 0x00 bytes just seen: 0x80 after zeros ends a sync packet, it is not a timestamp

    def feed(self, raw: bytes) -> list[ItmPacket]:
        self.buf += raw
        out: list[ItmPacket] = []
        b = self.buf
        i = 0
        while i < len(b):
            h = b[i]
            ss = h & 0x03
            if ss:                             # source packet: SS = payload size code, bit2 = 0 software / 1 hardware (DWT)
                n = SIZES[ss]
                if i + 1 + n > len(b):
                    break                      # incomplete: wait for more bytes
                if h & 0x04 == 0:
                    out.append(ItmPacket(h >> 3, bytes(b[i + 1:i + 1 + n])))
                else:
                    self.skipped += 1
                i += 1 + n
            elif h == 0x00:                    # sync (runs of zeros) or the start of one
                self.zeros += 1
                i += 1
                continue
            elif h == 0x80 and self.zeros:     # end of a sync packet
                i += 1
            elif h == 0x70:                    # overflow
                self.overflows += 1
                i += 1
            elif h & 0x0F == 0x00:             # local timestamp: format 1 (bit7 set) has continuation bytes
                j = i + 1
                if h & 0x80:
                    while j < len(b) and b[j] & 0x80:
                        j += 1
                    if j >= len(b):
                        break
                    j += 1
                i = j
            else:                              # extension / reserved header: skip one byte
                self.skipped += 1
                i += 1
            self.zeros = 0
        del b[:i]
        return out


class LineAssembler:
    """Turn stimulus-port text into cleaned lines per port."""

    def __init__(self, ports=(0,)):
        self.ports = set(ports)
        self.partial: dict[int, bytearray] = {}

    def feed(self, packets: list[ItmPacket]) -> list[tuple[int, str]]:
        lines = []
        for p in packets:
            if p.port not in self.ports:
                continue
            buf = self.partial.setdefault(p.port, bytearray())
            for byte in p.data:
                if byte == 0x0A:
                    lines.append((p.port, clean_line(bytes(buf))))
                    buf.clear()
                elif len(buf) < 4096:
                    buf.append(byte)
        return lines
