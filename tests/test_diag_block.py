import pytest

from rdt.diag_block import SIZE, DiagBlockError, decode, encode, read_consistent


def test_roundtrip_and_flags():
    raw = encode({"product": 5, "fw": "1.2.3", "seq": 10, "frames_ok": 99, "flags": 0b101, "stack_min_words_3": 77})
    b = decode(raw)
    assert len(raw) == SIZE and b["fw"] == "1.2.3" and b["frames_ok"] == 99
    assert b.flags == ["connected", "estop"] and b.stack_min_words[3] == 77


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: b"\0" + r[1:], "magic"),
    (lambda r: r[:-1] + bytes([r[-1] ^ 1]), "crc32"),
    (lambda r: r[:10], "need"),
])
def test_rejects_bad_blocks(mutate, msg):
    with pytest.raises(DiagBlockError, match=msg):
        decode(mutate(encode({"seq": 2})))


def test_odd_seq_is_a_torn_write():
    with pytest.raises(DiagBlockError, match="odd"):
        decode(encode({"seq": 3}))


def test_read_consistent_retries_on_seq_change():
    blocks = iter([encode({"seq": 2}), encode({"seq": 4}), encode({"seq": 6}), encode({"seq": 6})])
    assert read_consistent(lambda a, n: next(blocks), 0x20000000)["seq"] == 6
