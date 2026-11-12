"""Spike S4: can the ST-LINK V3 of the H755 board capture SWO/ITM? (decision 0004)

Default (read-only): print the trace-related registers of the robot and say what they mean.
--loopback  WRITES debug-trace registers of the robot MCU (ITM, TPIU; volatile, cleared by any reset) and writes a test string to
            ITM stimulus port 0 from the debugger, then reads it back through the ST-LINK SWO channel. Registers are restored to
            their previous values afterwards. It does not touch application memory, peripherals or clocks. Run only with the
            robot safe (wheels off the ground, someone at the robot) and the daemon stopped.
Usage: python -I scripts/s4_swo_probe.py [--loopback] [--cpu-hz 200000000] [--baud 2000000]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pyocd.core.helpers import ConnectHelper  # noqa: E402

from rdt.cli import load_targets  # noqa: E402
from rdt.swo import ItmDecoder, LineAssembler  # noqa: E402

R = dict(DEMCR=0xE000EDFC, ITM_STIM0=0xE0000000, ITM_TER=0xE0000E00, ITM_TPR=0xE0000E40, ITM_TCR=0xE0000E80,
         ITM_LAR=0xE0000FB0, TPIU_ACPR=0xE0040010, TPIU_SPPR=0xE00400F0, TPIU_FFCR=0xE0040304, TPIU_LAR=0xE0040FB0,
         DBGMCU_CR=0x5C001004, DWT_CTRL=0xE0001000)
PB3_MODER_MASK = 0x3 << 6


def show(t):
    for k in ("DEMCR", "ITM_TER", "ITM_TCR", "DWT_CTRL", "TPIU_ACPR", "TPIU_SPPR", "TPIU_FFCR", "DBGMCU_CR"):
        print(f"  {k:10} 0x{R[k]:08X} = 0x{t.read32(R[k]):08X}")
    moder = t.read32(0x58020400)
    afr = t.read32(0x58020420)
    print(f"  PB3 (SWO) mode={(moder >> 6) & 3} (2=alternate function) AF={(afr >> 12) & 0xF} (0=TRACESWO)")
    print(f"  ITM enabled: {bool(t.read32(R['ITM_TCR']) & 1)}; TRCENA: {bool(t.read32(R['DEMCR']) >> 24 & 1)}")


def loopback(sess, t, cpu_hz, baud):
    saved = {k: t.read32(R[k]) for k in ("ITM_TER", "ITM_TCR", "ITM_TPR", "TPIU_ACPR", "TPIU_SPPR", "TPIU_FFCR")}
    probe = sess.probe
    got = bytearray()
    try:
        probe.swo_start(baud)                       # ST-LINK starts listening at `baud`
        t.write32(R["ITM_LAR"], 0xC5ACCE55)         # unlock ITM
        t.write32(R["TPIU_LAR"], 0xC5ACCE55)        # unlock TPIU (if it has a lock register)
        t.write32(R["TPIU_SPPR"], 2)                # NRZ (UART style) SWO
        t.write32(R["TPIU_ACPR"], cpu_hz // baud - 1)
        t.write32(R["TPIU_FFCR"], 0x100)            # formatter off: raw ITM bytes
        t.write32(R["ITM_TPR"], 0xF)                # allow unprivileged access to ports 0..31 (harmless)
        t.write32(R["ITM_TCR"], (1 << 16) | 1)      # TraceBusID 1, ITMENA
        t.write32(R["ITM_TER"], 1)                  # stimulus port 0
        time.sleep(0.05)
        for ch in b"rdt swo loopback\n":
            for _ in range(200):                    # FIFO ready flag
                if t.read32(R["ITM_STIM0"]) & 1:
                    break
            t.write8(R["ITM_STIM0"], ch)            # 8-bit write: a one-byte ITM packet
        t0 = time.time()
        while time.time() - t0 < 1.5:
            got += bytes(probe.swo_read())
            time.sleep(0.05)
    finally:
        for k, v in saved.items():                  # restore
            t.write32(R[k], v)
        try:
            probe.swo_stop()
        except Exception:
            pass
    return bytes(got)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loopback", action="store_true")
    ap.add_argument("--cpu-hz", type=int, default=200_000_000)   # robot_s_rtos .ioc: SYSCLK 200 MHz
    ap.add_argument("--baud", type=int, default=2_000_000)
    a = ap.parse_args()
    cfg = load_targets()["robot"]
    sess = ConnectHelper.session_with_chosen_probe(unique_id=cfg["probe_serial"], connect_mode="attach", halt_on_connect=False,
                                                   resume_on_disconnect=False, auto_open=True,
                                                   options={"target_override": "cortex_m", "frequency": 4_000_000})
    with sess:
        t = sess.target
        print("state before:")
        show(t)
        if not a.loopback:
            return
        print(f"loopback: cpu {a.cpu_hz} Hz, SWO {a.baud} baud, ACPR {a.cpu_hz // a.baud - 1}")
        raw = loopback(sess, t, a.cpu_hz, a.baud)
        print("raw SWO bytes:", raw.hex() or "(none)")
        d = ItmDecoder()
        pk = d.feed(raw)
        lines = LineAssembler().feed(pk)
        print("decoded lines:", lines)
        print("state after (should equal before):")
        show(t)


if __name__ == "__main__":
    main()
