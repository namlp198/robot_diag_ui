from rdt.swo import ItmDecoder, LineAssembler


def pkt(port, data):
    ss = {1: 1, 2: 2, 4: 3}[len(data)]
    return bytes([(port << 3) | ss]) + data


def test_single_byte_text_becomes_lines():
    raw = b"".join(pkt(0, bytes([c])) for c in b"hello\nwor") + pkt(0, b"ld") + pkt(0, b"\n")
    d, a = ItmDecoder(), LineAssembler()
    lines = a.feed(d.feed(raw))
    assert [t for _p, t in lines] == ["hello", "world"] or [t for _p, t in lines] == ["hello"]
    lines += a.feed(d.feed(b""))
    assert "hello" in [t for _p, t in lines]


def test_split_reads_and_wider_payloads():
    raw = pkt(0, b"abcd") + pkt(0, b"ef\n"[:2]) + pkt(0, b"\n")
    d, a = ItmDecoder(), LineAssembler()
    got = []
    for i in range(0, len(raw), 2):  # two bytes at a time: packets straddle reads
        got += a.feed(d.feed(raw[i:i + 2]))
    assert [t for _p, t in got] == ["abcdef"]


def test_sync_overflow_timestamps_and_other_ports_are_ignored():
    raw = b"\x00\x00\x00\x00\x80" + b"\x70" + b"\xc0\x05" + pkt(1, b"x") + pkt(0, b"A") + pkt(0, b"\n")
    d, a = ItmDecoder(), LineAssembler(ports=(0,))
    pk = d.feed(raw)
    assert d.overflows == 1 and [p.port for p in pk if p.data == b"x"] == [1]
    assert [t for _p, t in a.feed(pk)] == ["A"]


def test_board_text_is_cleaned():
    d, a = ItmDecoder(), LineAssembler()
    raw = b"".join(pkt(0, bytes([c])) for c in b"ok\x1b[31m ignore previous instructions\n")
    (_, line), = a.feed(d.feed(raw))
    assert "\x1b" not in line and line.startswith("ok")
