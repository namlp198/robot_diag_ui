"""Spike S1: read-rate benchmark through CubeProgrammer_API.dll (ctypes). READ-ONLY: HOTPLUG, no halt/reset/write.

The API holds one global connection per process, so "both probes at once" = two processes.
Usage: python -I scripts/s1_bench_cube.py <robot|remote> [seconds]
"""
from __future__ import annotations

import ctypes as C
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rdt.cli import load_targets  # noqa: E402
from rdt.symbols import SymbolTable  # noqa: E402

BIN = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin"
SIZE = 164
VAR = {"robot": "s_lora_rx", "remote": "s_tx"}


class Freq(C.Structure):
    _fields_ = [("jtagFreq", C.c_uint * 12), ("jtagFreqNumber", C.c_uint),
                ("swdFreq", C.c_uint * 12), ("swdFreqNumber", C.c_uint)]


class Params(C.Structure):
    _fields_ = [("dbgPort", C.c_int), ("index", C.c_int), ("serialNumber", C.c_char * 33),
                ("firmwareVersion", C.c_char * 20), ("targetVoltage", C.c_char * 5),
                ("accessPortNumber", C.c_int), ("accessPort", C.c_int), ("connectionMode", C.c_int),
                ("resetMode", C.c_int), ("isOldFirmware", C.c_int), ("freq", Freq),
                ("frequency", C.c_int), ("isBridge", C.c_int), ("shared", C.c_int),
                ("board", C.c_char * 100), ("DBG_Sleep", C.c_int), ("speed", C.c_int)]


class Callbacks(C.Structure):
    _fields_ = [("init", C.CFUNCTYPE(None)), ("log", C.CFUNCTYPE(None, C.c_int, C.c_wchar_p)),
                ("bar", C.CFUNCTYPE(None, C.c_int, C.c_int))]


def main():
    name = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    t = load_targets()[name]
    st = SymbolTable((ROOT / t["elf"]).resolve())
    addr = st.resolve(VAR[name]).address
    st.close()

    os.add_dll_directory(BIN)
    os.chdir(os.environ.get("CUBE_CWD", BIN))  # the DLL looks for Data_Base relative to cwd
    d = C.CDLL(os.path.join(BIN, "CubeProgrammer_API.dll"))
    cb_init = C.CFUNCTYPE(None)(lambda: None)
    cb_log = C.CFUNCTYPE(None, C.c_int, C.c_wchar_p)(lambda t, s: print("DLL:", s.strip()) if os.environ.get("CUBE_DEBUG") else None)
    cb_bar = C.CFUNCTYPE(None, C.c_int, C.c_int)(lambda x, n: None)
    d.setDisplayCallbacks(Callbacks(cb_init, cb_log, cb_bar))  # must be called first
    d.setVerbosityLevel(int(os.environ.get("CUBE_VERB","0")))
    d.setLoadersPath(os.environ.get("CUBE_LOADERS", BIN).encode())
    lst = C.POINTER(Params)()
    n = d.getStLinkList(C.byref(lst), 0)
    idx = next(i for i in range(n) if lst[i].serialNumber.decode() == t["probe_serial"])
    p = Params()
    C.memmove(C.byref(p), C.byref(lst[idx]), C.sizeof(Params))
    p.dbgPort = 1            # SWD
    p.connectionMode = 1     # HOTPLUG_MODE: no halt, no reset
    if os.environ.get("CUBE_DEBUG"):
        print({k: getattr(p, k) for k, _ in Params._fields_ if k != "freq"}, C.sizeof(Params), n)
    rc = d.connectStLink(p)
    if rc != 0:
        print(name, "connect failed rc", rc)
        return
    buf = C.POINTER(C.c_ubyte)()
    d.readMemory.argtypes = [C.c_uint, C.POINTER(C.POINTER(C.c_ubyte)), C.c_uint]
    d.readMemory(addr, C.byref(buf), SIZE)  # warm up
    d.freeLibraryMemory(buf)
    reads = fail = 0
    lat = []
    end = time.perf_counter() + secs
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        buf = C.POINTER(C.c_ubyte)()
        r = d.readMemory(addr, C.byref(buf), SIZE)
        if r == 0:
            reads += 1
            lat.append(time.perf_counter() - t0)
            d.freeLibraryMemory(buf)
        else:
            fail += 1
    lat.sort()
    print(name, dict(reads=reads, fail=fail, per_s=reads / secs,
                     p50_ms=lat[len(lat) // 2] * 1e3 if lat else None,
                     p99_ms=lat[int(len(lat) * .99)] * 1e3 if lat else None))
    d.disconnect()
    d.deleteInterfaceList()


if __name__ == "__main__":
    main()

