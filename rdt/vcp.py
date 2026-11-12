"""Read-only VCP log reader. Only for targets whose `log_port` is set in targets.yaml.

The robot has `log_port: null` (USART3 is shared with the E22 receive path): this module refuses it.
Everything read from the port is data; lines are decoded leniently, control characters are replaced and
length is capped before the line goes anywhere (recorder, UI, prompt).
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable

MAX_LINE = 512
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class VcpError(Exception):
    pass


def clean_line(raw: bytes) -> str:
    s = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    s = _CTRL.sub("�", s)
    return s[:MAX_LINE]


def find_port(probe_serial: str) -> str:
    """COM port of the ST-LINK VCP with this probe serial (never guessed by order)."""
    try:
        from serial.tools import list_ports
    except ImportError as e:
        raise VcpError("pyserial is not installed: pip install -e .[probe]") from e
    for p in list_ports.comports():
        if p.serial_number == probe_serial:
            return p.device
    raise VcpError(f"no VCP for probe {probe_serial}")


class VcpReader(threading.Thread):
    def __init__(self, target: str, target_cfg: dict, sink: Callable[[str, float, str], None], t0: float,
                 on_error: Callable[[str, str], None] | None = None):
        if not target_cfg.get("log_port"):
            raise VcpError(f"target {target!r} has no log_port: its VCP must not be opened")
        super().__init__(name=f"vcp-{target}", daemon=True)
        self.target = target
        self.port = (find_port(target_cfg["probe_serial"]) if target_cfg["log_port"] == "auto"
                     else target_cfg["log_port"])
        self.baud = int(target_cfg.get("log_baud", 115200))
        self.sink = sink
        self.t0 = t0
        self.on_error = on_error or (lambda target, msg: None)
        self.stop_event = threading.Event()
        self.lines = 0

    def stop(self):
        self.stop_event.set()

    def run(self):
        import serial

        try:
            with serial.Serial(self.port, self.baud, timeout=0.2) as ser:
                buf = b""
                while not self.stop_event.is_set():
                    chunk = ser.read(256)
                    if not chunk:
                        continue
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.sink(self.target, time.perf_counter() - self.t0, clean_line(line))
                        self.lines += 1
                    if len(buf) > 4 * MAX_LINE:  # no newline for a long time: flush as one line
                        self.sink(self.target, time.perf_counter() - self.t0, clean_line(buf))
                        buf = b""
        except Exception as e:  # serial.SerialException and OS errors
            self.on_error(self.target, f"vcp {self.port}: {e}")
