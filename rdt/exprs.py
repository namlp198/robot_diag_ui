"""Live expressions: read-only watch of a named variable or a raw address, like the CubeIDE Live Expressions view.

An expression is either a variable path resolved from the flashed ELF (`s_lora_rx.filter.stats.lost`) or a number
(`0xE000ED28`) with a type and a count. Nothing here writes. Reads are limited to regions where a read is safe:
flash, SRAM and the Cortex-M private peripheral bus (SCB, DWT, NVIC: system registers whose reads have no side effect)
always; peripheral registers (0x40000000..0x5FFFFFFF) only when the user enabled `allow_peripheral_reads`, because reading
a status or data register can clear a flag or pop a FIFO byte; everything else is refused.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from .symbols import Resolved, SymbolError, SymbolTable

TYPES = {"u8": "B", "i8": "b", "u16": "H", "i16": "h", "u32": "I", "i32": "i", "u64": "Q", "i64": "q", "f32": "f", "f64": "d"}
SRAM = (0x20000000, 0x3FFFFFFF)
PPB = (0xE0000000, 0xE00FFFFF)
PERIPH = (0x40000000, 0x5FFFFFFF)
MAX_BYTES = 1024
MAX_EXPRS = 64
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
_NUM = re.compile(r"^(0[xX][0-9A-Fa-f]+|\d+)$")

# Handy names for the Cortex-M core registers (the same on the F446 and the H755 CM7). Address, type, meaning.
CORE_REGISTERS = [
    ("CPUID", 0xE000ED00, "u32", "CPU identification (part number, revision)"),
    ("ICSR", 0xE000ED04, "u32", "Interrupt control and state (VECTACTIVE = active exception)"),
    ("VTOR", 0xE000ED08, "u32", "Vector table offset"),
    ("SHCSR", 0xE000ED24, "u32", "System handler control and state (fault enables and pending)"),
    ("CFSR", 0xE000ED28, "u32", "Configurable fault status (MemManage, BusFault, UsageFault bits)"),
    ("HFSR", 0xE000ED2C, "u32", "HardFault status"),
    ("MMFAR", 0xE000ED34, "u32", "MemManage fault address"),
    ("BFAR", 0xE000ED38, "u32", "BusFault address"),
    ("DEMCR", 0xE000EDFC, "u32", "Debug exception and monitor control (TRCENA)"),
    ("DWT_CYCCNT", 0xE0001004, "u32", "Cycle counter (counts only if DWT is enabled)"),
    ("SYST_CVR", 0xE000E018, "u32", "SysTick current value"),
]


class ExprError(Exception):
    pass


@dataclass
class Expr:
    id: str
    target: str
    text: str
    address: int
    size: int
    type: str            # u8..f64 for a raw address, or the C type name for a variable
    count: int = 1
    resolved: Resolved | None = None

    def decode(self, raw: bytes):
        if self.resolved is not None:
            v = self.resolved.decode(raw)
            return v.hex() if isinstance(v, (bytes, bytearray)) else v
        fmt = "<" + TYPES[self.type] * self.count
        vals = list(struct.unpack(fmt, raw))
        return vals[0] if self.count == 1 else vals

    def info(self) -> dict:
        return {"id": self.id, "text": self.text, "address": self.address, "size": self.size, "type": self.type,
                "count": self.count, "symbol": self.resolved is not None,
                "kind": self.resolved.kind if self.resolved is not None else "raw"}


def check_region(cfg: dict, address: int, size: int, allow_peripherals: bool) -> None:
    end = address + size - 1
    lo, hi = cfg["flash_range"]
    inside = lambda a, b: a <= address and end <= b  # noqa: E731
    if inside(lo, hi) or inside(*SRAM) or inside(*PPB):
        return
    if inside(*PERIPH):
        if allow_peripherals:
            return
        raise ExprError("peripheral registers are not readable until you enable 'allow peripheral reads' in Settings: "
                        "a read can clear a flag or take a byte out of a FIFO")
    raise ExprError(f"0x{address:08X}..0x{end:08X} is not in flash, SRAM, the core registers or (when enabled) peripherals")


def build(target: str, cfg: dict, spec: dict, symtab: SymbolTable | None, allow_peripherals: bool) -> Expr:
    """`spec`: {id, text, type?, count?}. Raises ExprError with a message for the user."""
    eid, text = str(spec.get("id", "")), str(spec.get("text", "")).strip()
    if not _ID.match(eid):
        raise ExprError("bad id")
    if not text:
        raise ExprError("empty expression")
    if _NUM.match(text):
        typ = spec.get("type") or "u32"
        if typ not in TYPES:
            raise ExprError(f"type must be one of {', '.join(TYPES)}")
        try:
            count = int(spec.get("count") or 1)
        except (TypeError, ValueError):
            raise ExprError("count must be a number")
        size = struct.calcsize(TYPES[typ]) * count
        addr = int(text, 0)
        if count < 1 or size > MAX_BYTES:
            raise ExprError(f"at most {MAX_BYTES} bytes")
        if addr % struct.calcsize(TYPES[typ]):
            raise ExprError(f"address must be aligned to the type ({typ})")
        check_region(cfg, addr, size, allow_peripherals)
        return Expr(eid, target, text, addr, size, typ, count)
    if symtab is None:
        raise ExprError("no ELF available for this target")
    try:
        r = symtab.resolve(text)
    except SymbolError as e:
        raise ExprError(str(e))
    if r.size > MAX_BYTES:
        raise ExprError(f"{text} is {r.size} bytes; expand it with its members (at most {MAX_BYTES} bytes)")
    check_region(cfg, r.address, r.size, allow_peripherals)
    return Expr(eid, target, text, r.address, r.size, r.type_name, 1, r)
