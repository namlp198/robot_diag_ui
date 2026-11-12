import struct

from rdt import cantap
from rdt.symbols import Resolved

CFG = {"flash_range": [0x08000000, 0x080FFFFF]}


def test_describe_canopen_sdo():
    f = lambda cid, data, ext=False: {"id": cid, "ext": ext, "rtr": False, "data": bytes(data).hex()}  # noqa: E731
    assert cantap.describe(f(0x601, [0x40, 0x41, 0x60, 0x00, 0, 0, 0, 0])) == "SDO request node 1: read 0x6041:00"
    assert cantap.describe(f(0x602, [0x23, 0x40, 0x60, 0x00, 0x0F, 0, 0, 0])) == "SDO request node 2: write 0x6040:00 = 15 (0xF)"
    assert cantap.describe(f(0x602, [0x2B, 0xFF, 0x60, 0x00, 0x10, 0x27, 0, 0])) == "SDO request node 2: write 0x60FF:00 = 10000 (0x2710)"
    assert cantap.describe(f(0x581, [0x4B, 0x41, 0x60, 0x00, 0x37, 0x02, 0, 0])) == "SDO response node 1: read 0x6041:00 = 567 (0x237)"
    assert cantap.describe(f(0x581, [0x60, 0x40, 0x60, 0x00, 0, 0, 0, 0])) == "SDO response node 1: write OK 0x6040:00"
    assert "abort" in cantap.describe(f(0x581, [0x80, 0x00, 0x20, 0x00, 0x00, 0x00, 0x02, 0x06]))
    assert cantap.describe(f(0x701, [5])) == "heartbeat node 1"
    assert cantap.describe(f(0x000, [1, 1])) == "NMT"
    assert cantap.describe(f(0x1801D0EF, [0] * 8, ext=True)).startswith("29-bit 0x1801D0EF (J1939-style prio 6 PF 0x01")
    assert cantap.describe({"id": 0x123, "ext": False, "rtr": True, "data": ""}) == "remote request 0x123"


def hal_header(cid, ext=False, rtr=False, dlc=8, ts=0):
    # this HAL stores the DLC code unshifted (FDCAN_DLC_BYTES_8 == 8)
    return struct.pack("<10I", cid, cantap.HAL_EXT if ext else 0, cantap.HAL_RTR if rtr else 0, dlc, 0, 0, 0, ts, 0, 0)


def test_decode_hal_rx_header():
    f = cantap.decode_hal_rx(hal_header(0x581, dlc=8, ts=77), bytes([0x4B, 0x41, 0x60, 0, 1, 0, 0, 0]))
    assert f["dir"] == "rx" and f["id"] == 0x581 and f["dlc"] == 8 and f["ts"] == 77 and "read 0x6041" in f["label"]
    g = cantap.decode_hal_rx(hal_header(0x1801D0EF, ext=True, dlc=8), bytes(8))
    assert g["ext"] is True and g["id"] == 0x1801D0EF
    assert cantap.decode_hal_rx(bytes(40), bytes(8)) is None                        # untouched RAM: no frame yet
    assert cantap.decode_hal_rx(struct.pack("<10I", 1, 7, 0, 8, 0, 0, 0, 0, 0, 0), bytes(8)) is None  # implausible IdType
    # the header really read from the robot: 29-bit 0x18EFFF80, 3 bytes
    real = bytes.fromhex("80ffef18000000400000000003000000000000000000000000000000000000007f00000001000000")
    r = cantap.decode_hal_rx(real, bytes.fromhex("83c011ffff000f13"))
    assert r["id"] == 0x18EFFF80 and r["ext"] and r["dlc"] == 3 and r["data"] == "83c011" and "J1939-style" in r["label"]
    assert cantap.decode_hal_rx(b"short", bytes(8)) is None


def tx_element(cid, data, ext=False, dlc=None):
    n = len(data) if dlc is None else dlc
    t0 = (cid & 0x1FFFFFFF | cantap.HAL_EXT) if ext else (cid << 18)
    d = bytes(data).ljust(8, b"\0")
    return [t0, n << 16] + list(struct.unpack("<2I", d))


def test_decode_tx_element():
    f = cantap.decode_tx_element(tx_element(0x601, [0x40, 0x41, 0x60, 0, 0, 0, 0, 0]))
    assert f["dir"] == "tx" and f["id"] == 0x601 and f["dlc"] == 8 and "read 0x6041" in f["label"]
    assert cantap.decode_tx_element(tx_element(0x1ABCDEF, [1, 2], ext=True))["id"] == 0x1ABCDEF
    assert cantap.decode_tx_element([0, 0, 0, 0]) is None


class FakeBoard:
    """Memory with the RX header, a TX ring of 4 elements and the TXFQS register."""

    RX, RXD, RING, REGS = 0x24000100, 0x24000200, 0x4000AC00, 0x4000A000

    def __init__(self):
        self.rx = hal_header(0x581, dlc=8)
        self.rxd = bytes(8)
        self.ring = [tx_element(0, [], dlc=0)] * 4
        self.put = 0

    def queue(self, cid, data):
        self.ring[self.put] = tx_element(cid, data)
        self.put = (self.put + 1) % 4

    def read(self, addr, n):
        if addr == self.RX:
            return self.rx
        if addr == self.RXD:
            return self.rxd
        if addr == self.REGS + 0xC4:
            return ((self.put << 16) | (4 - 0)).to_bytes(4, "little")
        if addr == self.RING:
            return b"".join(struct.pack("<4I", *e) for e in self.ring)
        if addr == 0x24000300:  # hfdcan1.Instance
            return self.REGS.to_bytes(4, "little")
        if addr == 0x24000304:
            return self.RING.to_bytes(4, "little")
        if addr == 0x24000308:
            return (4).to_bytes(4, "little")      # TxElmtSize words
        if addr == 0x2400030C:
            return (4).to_bytes(4, "little")      # TxFifoQueueElmtsNbr
        raise AssertionError(hex(addr))


def tap_for(board, allow=True):
    v = {"RxHeader": Resolved("RxHeader", FakeBoard.RX, 40, "struct", "h"), "RxData": Resolved("RxData", FakeBoard.RXD, 8, "array", "u8"),
         "Instance": Resolved("i", 0x24000300, 4, "pointer", "p"), "TxFIFOQSA": Resolved("a", 0x24000304, 4, "uint", "u"),
         "TxElmtSize": Resolved("s", 0x24000308, 4, "uint", "u"), "TxFifoQueueElmtsNbr": Resolved("n", 0x2400030C, 4, "uint", "u")}
    return cantap.CanTap(v, CFG, allow)


def test_tap_reports_new_tx_elements_and_rx_changes():
    b = FakeBoard()
    tap = tap_for(b)
    frames, st = tap.poll(b.read, 0.0)                       # baseline: RX frame seen, TX ring baseline only
    assert [f["dir"] for f in frames] == ["rx"] and st["tx_reason"] is None
    b.queue(0x601, [0x40, 0x41, 0x60, 0, 0, 0, 0, 0])
    b.queue(0x602, [0x40, 0x41, 0x60, 0, 0, 0, 0, 0])
    frames, st = tap.poll(b.read, 0.1)
    assert [(f["dir"], f["id"]) for f in frames] == [("tx", 0x601), ("tx", 0x602)] and st["tx_frames"] == 2
    assert tap.poll(b.read, 0.2)[0] == []                    # nothing new: no duplicates
    b.rxd = bytes([0x4B, 0x41, 0x60, 0, 9, 0, 0, 0])
    assert [(f["dir"], f["data"][:2]) for f in tap.poll(b.read, 0.3)[0]] == [("rx", "4b")]
    for i in range(3):                                       # 3 of 4 slots: a lap warning is raised from n-1
        b.queue(0x601, [i])
    frames, st = tap.poll(b.read, 0.4)
    assert len(frames) == 3 and st["tx_possible_laps"] == 1


def test_tx_tap_is_off_without_the_peripheral_read_permission():
    b = FakeBoard()
    tap = tap_for(b, allow=False)
    frames, st = tap.poll(b.read, 0.0)
    assert [f["dir"] for f in frames] == ["rx"] and st["tx_reason"] == "peripheral_reads_off"
    b.queue(0x601, [1])
    assert tap.poll(b.read, 0.1)[0] == []                    # RX unchanged, TX not sampled


def test_tx_tap_waits_until_fdcan_is_initialised():
    b = FakeBoard()
    zero = b.read
    b.read = lambda a, n: bytes(4) if a in (0x24000300, 0x24000304) else zero(a, n)
    tap = tap_for(b)
    assert tap.poll(b.read, 0.0)[1]["tx_reason"] == "fdcan_not_initialised"
    b.read = zero
    for i in range(1, 25):                                   # retried every 20th poll
        tap.poll(b.read, i * 0.1)
    assert tap.ring is not None
