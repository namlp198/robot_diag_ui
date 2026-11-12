from rdt import rcl

# Example vectors from the (superseded) draft spec docs/rcl_protocol_v1_draft.md section 4.3, LINK_ID 0x1234
SPEC_VECTORS = [
    "A5 C3 10 01 34 12 07 0B 08 80 80 00 F0 F3 FF 01 02 80 80 48 9C",
    "A5 C3 10 01 34 12 08 0B 09 C8 80 01 F0 F3 FF 01 02 80 80 D1 FA",
    "A5 C3 10 01 34 12 09 0E 08 80 80 02 00 DC FF 01 02 80 80 02 01 3C 6D 63",
    "A5 C3 10 01 34 12 0A 07 08 80 80 30 FF FF FF 89 6A",
]


def test_spec_vectors_decode():
    for v in SPEC_VECTORS:
        d = rcl.decode(bytes.fromhex(v))
        assert d is not None and d["crc_ok"] and d["link_id"] == 0x1234 and d["type_name"] == "CONTROL", v


def frame(type_, link, seq, payload):
    body = bytes([0x10, type_]) + link.to_bytes(2, "little") + bytes([seq, len(payload)]) + payload
    return rcl.SOF + body + rcl.crc16(body).to_bytes(2, "little")


def test_crc_check_value():
    assert rcl.crc16(b"123456789") == 0x29B1


def test_parse_and_decode_control_frame():
    p = bytes([0x09, 200, 128]) + (0xFFFFFFFF & ~0b11).to_bytes(4, "little") + bytes([0x01, 2, 0x80, 0x80])
    raw = frame(0x01, 0x1234, 9, p)
    d = rcl.decode(raw)
    assert d["type_name"] == "CONTROL" and d["seq"] == 9 and d["link_id"] == 0x1234 and d["crc_ok"] and d["size"] == len(raw)
    assert d["payload"]["flags"] == ["ESTOP", "INPUT_VALID"]
    assert d["payload"]["drive_ud"] == 200 and d["payload"]["slots"]["LIGHT"] == "OFF" and d["payload"]["slots"]["SIREN"] == "absent"
    assert d["payload"]["tlv"][0]["name"] == "MONITOR_AXES" and d["payload"]["tlv"][0]["value"] == [128, 128]
    names = [f["name"] for f in d["fields"]]
    assert names == ["SOF", "VER", "TYPE", "LINK_ID", "SEQ", "LEN", "PAYLOAD", "CRC"]


def test_bad_crc_and_garbage_are_not_frames():
    raw = bytearray(frame(0x01, 1, 1, bytes(7)))
    raw[-1] ^= 1
    assert rcl.decode(bytes(raw)) is None
    assert rcl.parse_frame(bytes(raw), strict=False).crc_ok is False
    assert rcl.decode(b"\x00" * 58) is None
    assert rcl.decode(b"") is None
    assert rcl.parse_frame(b"\xA5\xC3\x10\x01\x01\x00\x01\x31" + bytes(60)) is None  # LEN 49


def test_frame_found_after_garbage_and_before_leftovers():
    good = frame(0x01, 7, 3, bytes([8, 128, 128, 0xFF, 0xFF, 0xFF, 0xFF]))
    buf = b"\x11\xA5\x22" + good + b"\xAA" * 5
    assert rcl.decode(buf)["seq"] == 3


def test_telemetry_decode():
    rec = bytes([0x01, 2]) + (-120 & 0xFFFF).to_bytes(2, "little") + bytes([0x40, 1, 87])
    p = bytes([0x41 & 0x01 | 0x40 | (1 << 4), 9, 255, 2]) + rec
    d = rcl.decode(frame(0x41, 5, 1, p))
    assert d["type_name"] == "TELEMETRY" and d["payload"]["control_source"] == "lora" and d["payload"]["link_quality"] is None
    assert "REMOTE_LINK_OK" in d["payload"]["robot_flags"] and "ESTOP_ACTIVE" in d["payload"]["robot_flags"]
    assert d["payload"]["records"][0] == {"id": 1, "name": "SPEED_RPM", "len": 2, "value": [-120]}
    assert d["payload"]["records"][1]["name"] == "BATT_PCT" and d["payload"]["records"][1]["value"] == [87]


def test_capture_dedups_and_reads_tx_length():
    cols = {"remote": ["s_tx.out.frame", "s_tx.out.frame_len"], "robot": ["s_lora_rx.parser.buf"]}
    cap = rcl.FrameCapture(cols)
    f1 = frame(0x01, 1, 1, bytes([8, 128, 128, 0xFF, 0xFF, 0xFF, 0xFF]))
    padded = (f1 + b"\x55" * 20).ljust(58, b"\0")
    assert [e["source"] for e in cap.feed("remote", 0.1, [padded.hex(), len(f1)])] == ["remote_tx"]
    assert cap.feed("remote", 0.2, [padded.hex(), len(f1)]) == []          # same frame again
    f2 = frame(0x01, 1, 2, bytes([8, 128, 128, 0xFF, 0xFF, 0xFF, 0xFF]))
    ev = cap.feed("remote", 0.3, [f2.ljust(58, b"\0").hex(), len(f2)])
    assert ev[0]["seq"] == 2 and ev[0]["link"] == "remote -> robot"
    assert cap.feed("remote", 0.4, [f2[:10].ljust(58, b"\0").hex(), len(f2)]) == []  # torn read: bad CRC, ignored
    rx = cap.feed("robot", 0.5, [f1.ljust(58, b"\0").hex()])
    assert rx[0]["source"] == "robot_rx" and rx[0]["seq"] == 1


def test_source_paths_cover_all_three_buffers():
    sp = rcl.source_paths()
    assert "s_tx.out.frame" in sp["remote"] and "s_rx.parser.buf" in sp["remote"] and "s_lora_rx.parser.buf" in sp["robot"]
