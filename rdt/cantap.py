"""CAN / FDCAN frame sampling on the robot (STM32H7 FDCAN1), read-only over SWD. Best effort, NOT a bus capture.

What is read, all by name from the flashed ELF (no hard-coded offsets):
  * RX: the firmware's `RxHeader` (HAL header of the last frame taken out of RX FIFO0) and `RxData[8]`: the last frame
    received. One slot, overwritten by every frame, so the poll sees a frame only if no newer one arrived since.
  * TX: the FDCAN TX FIFO in message RAM (`hfdcan1.msgRam.TxFIFOQSA`, `Init.TxFifoQueueElmtsNbr`, `Init.TxElmtSize`) plus the
    TXFQS register of the peripheral (`hfdcan1.Instance`): the put index tells how many frames were queued since the previous
    poll; the elements hold their contents (identifier, length, data). The ring holds only the last N frames, so when more than
    N were queued between two polls the older ones are lost (counted as "possible lap").
Never read: PSR (reading it resets its last-error code) and ECR (CEL clears on read) because they would change what the firmware
sees. Message RAM and peripheral registers are in the peripheral address range, so the TX tap needs "allow peripheral reads" in
Settings; without it only RX is sampled. Nothing is written.

A frame that arrives and is read by the firmware within one poll period is invisible here; for a complete log the firmware must
keep a ring of every frame (draft in outputs/claude_drafts/can_log_spec.md).
"""
from __future__ import annotations

from .backend import BackendError
from .exprs import ExprError, check_region
from .symbols import SymbolError, SymbolTable

TXFQS_OFFSET = 0xC4          # FDCAN_GlobalTypeDef.TXFQS (stm32h755xx.h)
HAL_STD, HAL_EXT = 0x00000000, 0x40000000
HAL_RTR = 0x20000000
HAL_FD = 0x00200000
HAL_BRS = 0x00100000
DLC_BYTES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]


def dlc_len(code: int) -> int:
    return DLC_BYTES[code & 0xF]


# --- identifiers and CANopen-style meaning -------------------------------------------------------------------------------
_FN = {0x000: "NMT", 0x080: "SYNC/EMCY", 0x100: "TIME", 0x180: "TPDO1", 0x200: "RPDO1", 0x280: "TPDO2", 0x300: "RPDO2",
       0x380: "TPDO3", 0x400: "RPDO3", 0x480: "TPDO4", 0x500: "RPDO4", 0x580: "SDO response", 0x600: "SDO request",
       0x700: "heartbeat"}
_SIZE_BY_N = {0: 4, 1: 3, 2: 2, 3: 1}


def describe(frame: dict) -> str:
    """Short meaning of a frame. Standard identifiers are read with the CANopen function-code layout (the DMKE drivers answer
    on 0x581/0x582 to requests on 0x601/0x602); anything else is only labelled by its width."""
    cid, data = frame["id"], bytes.fromhex(frame["data"])
    if frame["ext"]:  # read as J1939-style: priority (3 bits), PDU format, destination or group, source address
        pf, ps, sa, prio = (cid >> 16) & 0xFF, (cid >> 8) & 0xFF, cid & 0xFF, (cid >> 26) & 7
        dest = f"DA 0x{ps:02X}" if pf < 240 else f"PGN 0x{(cid >> 8) & 0x3FFFF:05X}"
        return f"29-bit 0x{cid:08X} (J1939-style prio {prio} PF 0x{pf:02X} {dest} SA 0x{sa:02X})"
    if frame["rtr"]:
        return f"remote request 0x{cid:03X}"
    fn, node = cid & 0x780, cid & 0x7F
    name = _FN.get(fn)
    if name is None:
        return f"0x{cid:03X}"
    base = f"{name} node {node}" if fn not in (0x000, 0x080, 0x100) else name
    if fn in (0x580, 0x600) and len(data) >= 4:
        cmd, idx, sub = data[0], int.from_bytes(data[1:3], "little"), data[3]
        obj = f"0x{idx:04X}:{sub:02X}"
        if fn == 0x600:  # client request
            ccs = cmd >> 5
            if ccs == 2:
                return f"{base}: read {obj}"
            if ccs == 1:
                size = _SIZE_BY_N.get((cmd >> 2) & 3, 4) if cmd & 3 == 3 else None
                val = int.from_bytes(data[4:4 + size], "little") if size and len(data) >= 4 + size else None
                return f"{base}: write {obj}" + (f" = {val} (0x{val:X})" if val is not None else "")
            return f"{base}: ccs {ccs} {obj}"
        scs = cmd >> 5  # server response
        if cmd == 0x80 or scs == 4:
            return f"{base}: abort {obj} code 0x{int.from_bytes(data[4:8], 'little'):08X}"
        if scs == 3:
            return f"{base}: write OK {obj}"
        if scs == 2:
            size = _SIZE_BY_N.get((cmd >> 2) & 3, 4) if cmd & 3 == 3 else min(4, len(data) - 4)
            val = int.from_bytes(data[4:4 + size], "little")
            return f"{base}: read {obj} = {val} (0x{val:X})"
    return base


# --- decoding of CAN elements --------------------------------------------------------------------------------------------
def _frame(direction: str, cid: int, ext: bool, rtr: bool, fd: bool, brs: bool, n: int, data: bytes, ts: int | None) -> dict:
    f = {"dir": direction, "id": cid, "ext": ext, "rtr": rtr, "fd": fd, "brs": brs, "dlc": n,
         "data": data[:n].hex(), "ts": ts}
    f["label"] = describe(f)
    return f


def decode_hal_rx(header: bytes, data: bytes) -> dict | None:
    """`FDCAN_RxHeaderTypeDef` (ten 32-bit words) + RxData."""
    if len(header) < 40:
        return None
    w = [int.from_bytes(header[i:i + 4], "little") for i in range(0, 40, 4)]
    cid, idtype, ftype, dlc, esi, brs, fdf, ts = w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[7]
    # In this HAL (stm32h7xx_hal_fdcan.c) DataLength is the plain DLC code 0..15 (FDCAN_DLC_BYTES_n = code), not shifted by 16.
    if idtype not in (HAL_STD, HAL_EXT) or ftype not in (0, HAL_RTR) or dlc > 15:
        return None  # not a plausible header (RAM not initialised yet)
    n = dlc_len(dlc)
    if cid == 0 and n == 0 and ts == 0 and idtype == HAL_STD:
        return None  # untouched header: no frame received yet
    return _frame("rx", cid, idtype == HAL_EXT, ftype == HAL_RTR, bool(fdf), bool(brs), n, data, ts & 0xFFFF)


def decode_tx_element(words: list[int]) -> dict | None:
    """One TX FIFO element of message RAM: T0 = ESI|XTD|RTR|ID, T1 = MM|EFC|FDF|BRS|DLC, then the data words."""
    if len(words) < 2:
        return None
    t0, t1 = words[0], words[1]
    ext, rtr = bool(t0 & HAL_EXT), bool(t0 & HAL_RTR)
    cid = (t0 & 0x1FFFFFFF) if ext else (t0 >> 18) & 0x7FF
    n = dlc_len((t1 >> 16) & 0xF)
    data = b"".join(w.to_bytes(4, "little") for w in words[2:])
    if n == 0 and cid == 0 and not rtr:
        return None  # zeroed element: never used
    return _frame("tx", cid, ext, rtr, bool(t1 & HAL_FD), bool(t1 & HAL_BRS), n, data, None)


# --- the tap ---------------------------------------------------------------------------------------------------------------
class CanTap:
    """Polled by the sampler of the robot on every tick. `poll(read, t)` returns (frames, stats)."""

    def __init__(self, vars_: dict, cfg: dict, allow_periph: bool):
        self.v = vars_
        self.cfg = cfg
        self.allow_periph = allow_periph
        self.tx_reason: str | None = None      # why TX is not sampled, if it is not
        self.ring: tuple[int, int, int, int] | None = None  # (regs_base, ring_addr, words, count)
        self.last_put: int | None = None
        self.last_rx: tuple | None = None
        self.stats = {"tx_frames": 0, "rx_frames": 0, "tx_possible_laps": 0, "tx_fifo_fill": None, "tx_reason": None, "polls": 0}

    def _word(self, read, key: str) -> int:
        r = self.v[key]
        return int.from_bytes(read(r.address, r.size), "little")

    def _setup_tx(self, read):
        if not self.allow_periph:
            self.tx_reason = "peripheral_reads_off"
            return
        try:
            regs = self._word(read, "Instance")
            ring = self._word(read, "TxFIFOQSA")
            words, count = self._word(read, "TxElmtSize"), self._word(read, "TxFifoQueueElmtsNbr")
            if not (0 < count <= 32 and 2 <= words <= 18 and regs and ring):
                self.tx_reason = "fdcan_not_initialised"
                return
            check_region(self.cfg, regs + TXFQS_OFFSET, 4, True)
            check_region(self.cfg, ring, count * words * 4, True)
            self.ring, self.tx_reason = (regs, ring, words, count), None
        except (ExprError, KeyError, BackendError) as e:
            self.tx_reason = f"tx_tap_unavailable: {str(e)[:80]}"

    def poll(self, read, t: float) -> tuple[list[dict], dict]:
        out: list[dict] = []
        self.stats["polls"] += 1
        # RX: the last frame received
        try:
            hdr = read(self.v["RxHeader"].address, self.v["RxHeader"].size)
            data = read(self.v["RxData"].address, self.v["RxData"].size) if "RxData" in self.v else b"\0" * 8
            f = decode_hal_rx(hdr, data)
            if f is not None:
                key = (f["id"], f["data"], f["ts"], f["dlc"])
                if key != self.last_rx:
                    self.last_rx = key
                    self.stats["rx_frames"] += 1
                    out.append(f)
        except BackendError:
            pass
        # TX: new elements of the TX FIFO since the previous poll
        if self.ring is None and self.tx_reason != "peripheral_reads_off" and self.stats["polls"] % 20 == 1:
            self._setup_tx(read)  # first poll, then every 20th until FDCAN is initialised
        if self.ring is not None:
            regs, ring, words, count = self.ring
            try:
                txfqs = int.from_bytes(read(regs + TXFQS_OFFSET, 4), "little")
                put = (txfqs >> 16) & 0x1F
                self.stats["tx_fifo_fill"] = count - (txfqs & 0x3F)  # elements waiting to be sent
                raw = read(ring, count * words * 4)
                if self.last_put is not None and put < count:
                    k = (put - self.last_put) % count
                    for i in range(k):
                        idx = (self.last_put + i) % count
                        el = [int.from_bytes(raw[idx * words * 4 + j * 4: idx * words * 4 + j * 4 + 4], "little") for j in range(words)]
                        f = decode_tx_element(el)
                        if f is not None:
                            self.stats["tx_frames"] += 1
                            out.append(f)
                    if k >= count - 1:
                        self.stats["tx_possible_laps"] += 1
                if put < count:
                    self.last_put = put
            except BackendError:
                pass
        self.stats["tx_reason"] = self.tx_reason
        return out, dict(self.stats)


def build(cfg: dict, symtab: SymbolTable, allow_periph: bool) -> CanTap | None:
    """None when the firmware has no FDCAN1 handle or no RX header variable."""
    try:
        v = {"RxHeader": symtab.resolve("RxHeader"), "Instance": symtab.resolve("hfdcan1.Instance"),
             "TxFIFOQSA": symtab.resolve("hfdcan1.msgRam.TxFIFOQSA"), "TxElmtSize": symtab.resolve("hfdcan1.Init.TxElmtSize"),
             "TxFifoQueueElmtsNbr": symtab.resolve("hfdcan1.Init.TxFifoQueueElmtsNbr")}
    except SymbolError:
        return None
    try:
        v["RxData"] = symtab.resolve("RxData")
    except SymbolError:
        pass
    return CanTap(v, cfg, allow_periph)
