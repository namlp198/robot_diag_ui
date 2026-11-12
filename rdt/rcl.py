"""RCL v1 frame decoding (spec: robot_link/spec/rcl_v1.md, C: robot_rc_rtos/App/Protocol/rcl/rcl_ids.h) and frame capture.

Pure Python, no hardware. A frame is `A5 C3 VER TYPE LINK_ID(le16) SEQ LEN PAYLOAD CRC16(le)`, CRC-16/CCITT-FALSE over
bytes 2..8+LEN-1. Bytes read from a board's buffer are data: they are decoded, never executed, and frames that do not
pass the CRC are not reported as frames (a read can catch a buffer while the firmware is rewriting it).

Capture: the firmware keeps the last frame it sent (`s_tx.out.frame`) and the byte buffer of each parser
(`s_lora_rx.parser.buf`, `s_rx.parser.buf`). The daemon samples those buffers; it sees a frame only if it is still in the
buffer when polled, so at a poll rate below the frame rate some frames are never seen (SEQ gaps tell how many).
"""
from __future__ import annotations

from dataclasses import dataclass

SOF = b"\xA5\xC3"
HEADER = 8
MAX_PAYLOAD = 48
MAX_FRAME = 58

TYPES = {0x01: "CONTROL", 0x02: "REMOTE_INFO", 0x03: "PAIR_REQUEST", 0x41: "TELEMETRY", 0x42: "ROBOT_INFO", 0x43: "PAIR_ACCEPT"}
CONTROL_FLAGS = {0x01: "ESTOP", 0x02: "RESET_FAULT", 0x04: "SRC_APP", 0x08: "INPUT_VALID"}
SLOTS = ["LIGHT", "SIREN", "NOZZLE", "VALVE_PROTECT", "VALVE_MONITOR", "WINCH", "DOZER", "BRAKE", "SPEED_LEVEL", "OSCILLATE", "FAN"]
SLOT_STATE = {0: "OFF", 1: "A", 2: "B", 3: "absent"}
CONTROL_TLV = {0x01: "MONITOR_AXES", 0x02: "FAN_SPEED", 0x03: "AUX_AXES"}
RFLAGS = {0x01: "ESTOP_ACTIVE", 0x02: "MOTOR_FAULT", 0x04: "DRIVER_ENABLED", 0x08: "OVERCURRENT", 0x40: "REMOTE_LINK_OK"}
SOURCE = {0: "none", 1: "lora", 2: "host", 3: "local"}
RECORDS = {  # id -> (name, struct format of the value, little-endian)
    0x01: ("SPEED_RPM", "<h"), 0x02: ("DISTANCE_MM", "<H"), 0x03: ("OUTPUT_STATE", "<I"), 0x04: ("MOTOR_STATUS", "<B"),
    0x10: ("DRIVE_FAULT", "<HH"), 0x11: ("DRIVE_ERR_BYTES", "<BBBBBB"), 0x12: ("DRIVE_CURRENT", "<HH"),
    0x13: ("DRIVE_VOLTAGE", "<HH"), 0x14: ("DRIVE_TEMP", "<bb"), 0x15: ("MOTOR_TEMP", "<b"),
    0x20: ("GAS_CO", "<H"), 0x21: ("GAS_O2", "<H"), 0x22: ("GAS_LEL", "<H"), 0x23: ("GAS_H2S", "<H"), 0x24: ("GAS_CO2", "<H"),
    0x25: ("STEAM", "<H"), 0x30: ("TEMP_ENV", "<h"), 0x31: ("ATTITUDE", "<hhh"), 0x40: ("BATT_PCT", "<B"),
    0x41: ("BATT_TEMP", "<b"), 0x50: ("FAN_FEEDBACK", "<BB"),
}


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, xorout 0). crc16(b'123456789') == 0x29B1."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass
class Frame:
    raw: bytes
    version: int
    type: int
    link_id: int
    seq: int
    length: int
    payload: bytes
    crc: int
    crc_ok: bool

    @property
    def type_name(self) -> str:
        return TYPES.get(self.type & 0x7F, f"0x{self.type:02X}") if not self.type & 0x80 else f"0x{self.type:02X} (auth bit)"


def parse_frame(buf: bytes, strict: bool = True) -> Frame | None:
    """One frame at the start of `buf` (which must begin with A5 C3). None if it is incomplete or malformed;
    with strict=True also None when the CRC is wrong."""
    if len(buf) < HEADER + 2 or buf[:2] != SOF:
        return None
    n = buf[7]
    if n > MAX_PAYLOAD or len(buf) < HEADER + n + 2:
        return None
    raw = bytes(buf[:HEADER + n + 2])
    crc = int.from_bytes(raw[-2:], "little")
    ok = crc16(raw[2:-2]) == crc
    if strict and not ok:
        return None
    return Frame(raw, raw[2], raw[3], int.from_bytes(raw[4:6], "little"), raw[6], n, raw[HEADER:HEADER + n], crc, ok)


def find_frame(buf: bytes) -> Frame | None:
    """First CRC-valid frame inside a parser buffer (scans for SOF; the buffer may hold leftovers after the frame)."""
    i = buf.find(SOF)
    while i != -1:
        f = parse_frame(buf[i:])
        if f:
            return f
        i = buf.find(SOF, i + 1)
    return None


def _flags(v: int, table: dict) -> list[str]:
    return [n for bit, n in table.items() if v & bit]


def decode_payload(f: Frame) -> dict:
    p, t = f.payload, f.type
    if t == 0x01 and len(p) >= 7:
        packed = int.from_bytes(p[3:7], "little")
        out = {"flags": _flags(p[0], CONTROL_FLAGS), "flags_raw": p[0], "drive_ud": p[1], "drive_lr": p[2],
               "slots": {SLOTS[i] if i < len(SLOTS) else f"slot{i}": SLOT_STATE[(packed >> (2 * i)) & 3] for i in range(16)
                         if i < len(SLOTS) or (packed >> (2 * i)) & 3 != 3}, "tlv": []}
        i = 7
        while i + 2 <= len(p):
            tid, ln = p[i], p[i + 1]
            if i + 2 + ln > len(p):
                out["tlv"].append({"id": tid, "error": "runs past the end of the payload"})
                break
            out["tlv"].append({"id": tid, "name": CONTROL_TLV.get(tid, "unknown"), "value": list(p[i + 2:i + 2 + ln])})
            i += 2 + ln
        return out
    if t == 0x41 and len(p) >= 4:
        out = {"robot_flags": _flags(p[0], RFLAGS), "robot_flags_raw": p[0], "control_source": SOURCE[(p[0] >> 4) & 3],
               "ack_seq": p[1], "link_quality": None if p[2] == 255 else p[2], "page": p[3], "records": []}
        i = 4
        while i + 2 <= len(p):
            rid, ln = p[i], p[i + 1]
            if i + 2 + ln > len(p):
                out["records"].append({"id": rid, "error": "runs past the end of the payload"})
                break
            raw = p[i + 2:i + 2 + ln]
            name, fmt = RECORDS.get(rid, ("unknown", ""))
            rec = {"id": rid, "name": name, "len": ln}
            try:
                import struct
                rec["value"] = list(struct.unpack(fmt, raw)) if fmt and struct.calcsize(fmt) == ln else list(raw)
            except Exception:
                rec["value"] = list(raw)
            out["records"].append(rec)
            i += 2 + ln
        return out
    if t in (0x02, 0x42) and len(p) >= 15:
        return {"device_kind": {1: "remote", 2: "robot"}.get(p[0], p[0]), "product_id": p[1], "hw_rev": p[2],
                "fw": f"{p[3]}.{p[4]}.{p[5]}", "protocol_minor": p[6], "slot_mask": int.from_bytes(p[7:11], "little"),
                "uid_hash_low": int.from_bytes(p[11:15], "little")}
    return {}


def decode(buf: bytes) -> dict | None:
    """Decoded view of the CRC-valid frame in `buf`, or None."""
    f = find_frame(buf)
    return None if f is None else describe(f)


def describe(f: Frame) -> dict:
    fields = [("SOF", 0, 2), ("VER", 2, 1), ("TYPE", 3, 1), ("LINK_ID", 4, 2), ("SEQ", 6, 1), ("LEN", 7, 1),
              ("PAYLOAD", 8, f.length), ("CRC", 8 + f.length, 2)]
    return {"hex": f.raw.hex(), "version": f"{f.version >> 4}.{f.version & 15}", "type_id": f.type, "type_name": f.type_name,  # not "type": the daemon's WebSocket message uses that key
            "link_id": f.link_id, "seq": f.seq, "length": f.length, "crc": f.crc, "crc_ok": f.crc_ok, "size": len(f.raw),
            "fields": [{"name": n, "offset": o, "size": s} for n, o, s in fields if s], "payload": decode_payload(f)}


# --- capture ----------------------------------------------------------------------------------------------------
# Where the frames are: (target, side, buffer path, length path or None). `tx`: the buffer holds the frame as sent
# (length given); `rx`: parser buffer, the frame is looked for inside it.
SOURCES = [
    {"id": "remote_tx", "target": "remote", "side": "tx", "buf": "s_tx.out.frame", "len": "s_tx.out.frame_len",
     "link": "remote -> robot"},
    {"id": "robot_rx", "target": "robot", "side": "rx", "buf": "s_lora_rx.parser.buf", "len": None, "link": "remote -> robot"},
    {"id": "remote_rx", "target": "remote", "side": "rx", "buf": "s_rx.parser.buf", "len": None, "link": "robot -> remote"},
]


def source_paths() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in SOURCES:
        out.setdefault(s["target"], []).extend(p for p in (s["buf"], s["len"]) if p)
    return out


class FrameCapture:
    """Turns a stream of samples into frame events: one per distinct CRC-valid frame seen in a source's buffer."""

    def __init__(self, columns: dict[str, list[str]]):
        self.cols = columns
        self.last: dict[str, bytes] = {}
        self.active = [s for s in SOURCES if s["target"] in columns and s["buf"] in columns[s["target"]]]

    def feed(self, target: str, t: float, vals: list) -> list[dict]:
        out = []
        cols = self.cols.get(target, [])
        for s in self.active:
            if s["target"] != target:
                continue
            try:
                raw = bytes.fromhex(vals[cols.index(s["buf"])])
                if s["len"] and s["len"] in cols:
                    n = vals[cols.index(s["len"])]
                    raw = raw[:n] if isinstance(n, int) and 0 < n <= MAX_FRAME else b""
                f = parse_frame(raw) if s["side"] == "tx" else find_frame(raw)
            except (ValueError, TypeError, IndexError):
                continue
            if f is None or self.last.get(s["id"]) == f.raw:
                continue
            self.last[s["id"]] = f.raw
            d = describe(f)
            out.append({"source": s["id"], "target": target, "side": s["side"], "link": s["link"], "t": round(t, 6), **d})
        return out
