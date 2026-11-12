"""Polls named variables of one target over SWD (read-only) at a fixed rate and hands samples to a callback."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from .backend import BackendError, Probe
from .symbols import Resolved, SymbolTable
from .verify import VerifyResult, verify

Sink = Callable[[str, float, list], None]  # (target, t_seconds_since_t0, values)


def to_cell(x):
    """Value as stored in a sample: bytes become hex, everything else is left as is."""
    return x.hex() if isinstance(x, (bytes, bytearray)) else x


class Sampler(threading.Thread):
    def __init__(self, name: str, serial: str, elf: Path, paths: list[str], hz: float,
                 sink: Sink, t0: float, on_error: Callable[[str, str], None] | None = None,
                 image: Path | None = None):
        super().__init__(name=f"sampler-{name}", daemon=True)
        self.target = name
        self.serial = serial
        self.paths = list(paths)
        self.hz = hz
        self.sink = sink
        self.t0 = t0
        self.on_error = on_error or (lambda target, msg: None)
        self.stop_event = threading.Event()
        self.reads = 0
        self.failures = 0
        self.expr_sink: Callable[[str, float, dict], None] | None = None  # live expressions: (target, t, {id: value})
        self._exprs: list = []
        self._expr_lock = threading.Lock()
        self.elf = Path(elf)
        self.image = Path(image) if image else self.elf  # the ELF that is really flashed (may lack DWARF)
        self.fw: VerifyResult | None = None  # set after attach: does the board run this ELF?
        st = SymbolTable(elf, addr_from=image)
        try:
            self.vars: list[Resolved] = [st.resolve(p) for p in self.paths]
        finally:
            st.close()

    def stop(self):
        self.stop_event.set()

    def set_exprs(self, exprs: list):
        """Live expressions (rdt.exprs.Expr) read on every tick, besides the watched variables."""
        with self._expr_lock:
            self._exprs = list(exprs)

    def set_tap(self, tap, sink: Callable[[str, float, list, dict], None]):
        """A frame tap (rdt.cantap.CanTap): polled on every tick; `sink(target, t, frames, stats)` gets what it saw."""
        self._tap, self._tap_sink = tap, sink

    def _poll_tap(self, probe, t: float):
        tap = getattr(self, "_tap", None)
        if tap is None:
            return
        try:
            frames, stats = tap.poll(probe.read, t)
        except Exception as err:  # a tap bug must not stop the sampling of the watched variables
            self.on_error(self.target, f"can tap: {str(err)[:120]}")
            self._tap = None
            return
        self._tap_sink(self.target, t, frames, stats)

    def _read_exprs(self, probe, t: float):
        with self._expr_lock:
            ex = list(self._exprs)
        if not ex or self.expr_sink is None:
            return
        res = {}
        for e in ex:
            try:
                res[e.id] = e.decode(probe.read(e.address, e.size))
            except Exception as err:  # a refused read must not stop the sampling of the watched variables
                res[e.id] = {"error": str(err)[:200]}
        self.expr_sink(self.target, t, res)

    def run(self):
        period = 1.0 / self.hz
        try:
            with Probe(self.serial) as probe:
                self.fw = verify(probe.read, self.image)
                if not self.fw.ok:
                    self.on_error(self.target, self.fw.summary())
                while not self.stop_event.is_set():
                    tick = time.perf_counter()
                    try:
                        vals = [to_cell(v.decode(probe.read(v.address, v.size))) for v in self.vars]
                    except BackendError as e:
                        self.failures += 1
                        self.on_error(self.target, str(e))
                    else:
                        self.reads += 1
                        self.sink(self.target, tick - self.t0, vals)
                    self._read_exprs(probe, tick - self.t0)
                    self._poll_tap(probe, tick - self.t0)
                    self.stop_event.wait(max(0.0, period - (time.perf_counter() - tick)))
        except BackendError as e:
            self.on_error(self.target, str(e))
