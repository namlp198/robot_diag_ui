"""Generate scripts/robot_diag.ico (a green ">_" prompt on the dark theme colour). Pure standard library: PNG-in-ICO, 256 and 48 px.
Usage: python -I scripts/make_icon.py"""
import struct
import zlib
from pathlib import Path

BG, FG, EDGE = (7, 6, 13), (0, 255, 163), (166, 107, 255)


def png(size: int) -> bytes:
    s = size
    rows = []
    t = max(2, s // 14)                       # stroke thickness
    for y in range(s):
        row = bytearray([0])
        for x in range(s):
            u, v = x / s, y / s
            r = 0.12                           # rounded-square mask
            cx, cy = min(max(u, r), 1 - r), min(max(v, r), 1 - r)
            inside = (u - cx) ** 2 + (v - cy) ** 2 <= r * r
            col, a = BG, 255 if inside else 0
            if inside:
                if min(u, v, 1 - u, 1 - v) < 0.035:
                    col = EDGE
                # ">" : two strokes from (0.26,0.3) to (0.5,0.5) to (0.26,0.7)
                for (x0, y0, x1, y1) in ((0.26, 0.30, 0.50, 0.50), (0.50, 0.50, 0.26, 0.70)):
                    dx, dy = x1 - x0, y1 - y0
                    tt = max(0.0, min(1.0, ((u - x0) * dx + (v - y0) * dy) / (dx * dx + dy * dy)))
                    if ((u - x0 - tt * dx) ** 2 + (v - y0 - tt * dy) ** 2) ** 0.5 < t / s:
                        col = FG
                # "_"
                if 0.56 <= u <= 0.78 and 0.66 <= v <= 0.66 + 1.6 * t / s:
                    col = FG
            row += bytes((*col, a))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(sizes=(256, 48)) -> bytes:
    images = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return head + entries + b"".join(images)


if __name__ == "__main__":
    out = Path(__file__).with_name("robot_diag.ico")
    out.write_bytes(ico())
    print("wrote", out, out.stat().st_size, "bytes")
