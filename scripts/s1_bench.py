"""Spike S1: SWD read-rate benchmark through pyOCD. READ-ONLY: attach mode, no halt, no reset, no write.

Usage: python -I scripts/s1_bench.py once              # one read per probe, print bytes
       python -I scripts/s1_bench.py solo [seconds]     # each probe alone
       python -I scripts/s1_bench.py both [seconds]     # both probes at the same time
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyocd.core.helpers import ConnectHelper  # noqa: E402

from rdt.cli import load_targets  # noqa: E402
from rdt.symbols import SymbolTable  # noqa: E402

SIZE = 164  # s_lora_rx on the robot; the remote has no such variable, so it reads 164 B of s_tx


def plan() -> dict:
    t = load_targets()
    out = {}
    for name, var in (("robot", "s_lora_rx"), ("remote", "s_tx")):
        st = SymbolTable((ROOT / t[name]["elf"]).resolve())
        r = st.resolve(var)
        st.close()
        out[name] = (t[name]["probe_serial"], r.address)
    return out


def open_session(serial: str):
    # attach: do not halt, do not reset; leave the core as it is on disconnect.
    return ConnectHelper.session_with_chosen_probe(
        unique_id=serial, connect_mode="attach", halt_on_connect=False,
        resume_on_disconnect=False, auto_open=True,
        # target_override=cortex_m: no CMSIS pack needed (pyOCD has no built-in stm32h755); memory reads only.
        options={"frequency": 4_000_000, "target_override": "cortex_m"},
    )


def bench(name: str, serial: str, addr: int, seconds: float, result: dict, barrier=None):
    with open_session(serial) as sess:
        tgt = sess.target
        tgt.read_memory_block8(addr, SIZE)  # warm up
        if barrier:
            barrier.wait()
        n = fail = 0
        lat = []
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            t0 = time.perf_counter()
            try:
                tgt.read_memory_block8(addr, SIZE)
                n += 1
                lat.append(time.perf_counter() - t0)
            except Exception:
                fail += 1
        el = seconds
        lat.sort()
        result[name] = dict(reads=n, fail=fail, per_s=n / el,
                            p50_ms=lat[len(lat) // 2] * 1e3 if lat else None,
                            p99_ms=lat[int(len(lat) * .99)] * 1e3 if lat else None)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    p = plan()
    for k, (s, a) in p.items():
        print(f"{k}: probe {s} addr 0x{a:08X} size {SIZE}")
    if mode == "once":
        for k, (s, a) in p.items():
            with open_session(s) as sess:
                data = sess.target.read_memory_block8(a, SIZE)
                print(k, "core state:", sess.target.get_state().name, "first16:", bytes(data[:16]).hex())
    elif mode == "solo":
        for k, (s, a) in p.items():
            r = {}
            bench(k, s, a, secs, r)
            print("solo", k, r[k])
    elif mode == "both":
        r: dict = {}
        bar = threading.Barrier(len(p))
        th = [threading.Thread(target=bench, args=(k, s, a, secs, r, bar)) for k, (s, a) in p.items()]
        [t.start() for t in th]
        [t.join() for t in th]
        for k in p:
            print("both", k, r.get(k))


if __name__ == "__main__":
    main()
