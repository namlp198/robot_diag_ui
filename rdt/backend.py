"""Read-only SWD backend on pyOCD (decision 0001). Attach only: never halts, resets or writes target memory."""
from __future__ import annotations

import threading
import time


class BackendError(Exception):
    pass


class Probe:
    """One ST-LINK, one pyOCD session. Reads are serialised by a lock so several callers may share it."""

    def __init__(self, serial: str, frequency: int = 4_000_000):
        self.serial = serial
        self.frequency = frequency
        self._lock = threading.Lock()
        self._session = None

    def open(self) -> "Probe":
        try:
            from pyocd.core.helpers import ConnectHelper
        except ImportError as e:  # pyocd is an optional dependency ("probe" extra)
            raise BackendError("pyocd is not installed: pip install -e .[probe]") from e
        s = ConnectHelper.session_with_chosen_probe(
            unique_id=self.serial, connect_mode="attach", halt_on_connect=False,
            resume_on_disconnect=False, auto_open=False, return_first=False,
            options={"frequency": self.frequency, "target_override": "cortex_m"},
        )
        if s is None:
            raise BackendError(f"no probe with serial {self.serial}")
        try:
            s.open()
        except Exception as e:
            raise BackendError(f"attach to {self.serial} failed: {e}") from e
        self._session = s
        return self

    def read(self, address: int, size: int) -> bytes:
        if self._session is None:
            raise BackendError("probe not open")
        with self._lock:
            try:
                return bytes(self._session.target.read_memory_block8(address, size))
            except Exception as e:
                raise BackendError(f"read 0x{address:08X}+{size} failed: {e}") from e

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()


def list_serials() -> list[str]:
    from pyocd.probe.aggregator import DebugProbeAggregator
    return [p.unique_id for p in DebugProbeAggregator.get_all_connected_probes(unique_id=None)]


def now() -> float:
    """PC monotonic timestamp; the boards do not share a clock."""
    return time.perf_counter()
