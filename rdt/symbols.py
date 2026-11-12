"""Resolve variable paths (``s_lora_rx.filter.stats.lost``) to address/size/type from ELF DWARF.

No offsets are hard-coded: everything comes from the ELF that was flashed.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from elftools.elf.elffile import ELFFile

_TOKEN = re.compile(r"\.?([A-Za-z_]\w*)|\[(\d+)\]")
_STRUCTS = ("DW_TAG_structure_type", "DW_TAG_union_type")
_QUALIFIERS = ("DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_restrict_type")


class SymbolError(Exception):
    pass


@dataclass(frozen=True)
class Resolved:
    path: str
    address: int
    size: int
    kind: str  # int | uint | float | bool | enum | pointer | struct | array | bytes
    type_name: str

    def decode(self, raw: bytes):
        if len(raw) != self.size:
            raise SymbolError(f"{self.path}: expected {self.size} bytes, got {len(raw)}")
        if self.kind in ("uint", "enum", "pointer", "bool"):
            v = int.from_bytes(raw, "little")
            return bool(v) if self.kind == "bool" else v
        if self.kind == "int":
            return int.from_bytes(raw, "little", signed=True)
        if self.kind == "float":
            return struct.unpack("<f" if self.size == 4 else "<d", raw)[0]
        return raw


class SymbolTable:
    def __init__(self, elf_path: str | Path, addr_from: str | Path | None = None):
        """Types (and addresses) from `elf_path`. With `addr_from` (the ELF that is really flashed, e.g. a Release
        build without DWARF) the addresses come from its .symtab and the types stay from `elf_path`; a variable
        whose size differs between the two is refused, so a layout change cannot go unnoticed."""
        self.elf_path = Path(elf_path)
        self._fh = open(self.elf_path, "rb")
        self._elf = ELFFile(self._fh)
        if not self._elf.has_dwarf_info():
            raise SymbolError(f"{self.elf_path}: no DWARF info (build with -g)")
        self._dwarf = self._elf.get_dwarf_info()
        self._vars: dict[str, tuple[object, int]] = {}
        self._index()
        if addr_from is not None:
            self._rebase(Path(addr_from))

    def close(self):
        self._fh.close()

    def _index(self):
        for cu in self._dwarf.iter_CUs():
            for die in cu.iter_DIEs():
                if die.tag != "DW_TAG_variable" or "DW_AT_name" not in die.attributes:
                    continue
                addr = self._static_address(die.attributes.get("DW_AT_location"))
                if addr is None:
                    continue
                self._vars.setdefault(die.attributes["DW_AT_name"].value.decode(), (die, addr))

    def _rebase(self, image_elf: Path):
        found: dict[str, list[tuple[int, int]]] = {}
        with open(image_elf, "rb") as fh:
            tab = ELFFile(fh).get_section_by_name(".symtab")
            if tab is None:
                raise SymbolError(f"{image_elf}: no .symtab (stripped?)")
            for sym in tab.iter_symbols():
                if sym["st_info"]["type"] == "STT_OBJECT" and sym.name:
                    found.setdefault(sym.name, []).append((sym["st_value"], sym["st_size"]))
        rebased = {}
        for name, (die, _old) in self._vars.items():
            cands = set(found.get(name, []))
            if len(cands) != 1:
                continue  # absent in the flashed image, or ambiguous (same static name twice): not offered
            addr, size = next(iter(cands))
            try:
                dsize = self._size(self._type_die(die))
            except SymbolError:
                continue
            if size and dsize and size != dsize:
                continue  # layout differs between the type ELF and the flashed image
            rebased[name] = (die, addr)
        self._vars = rebased

    @staticmethod
    def _static_address(loc) -> int | None:
        # DW_OP_addr (0x03) followed by a 4-byte little-endian address (ARM32)
        if loc is None or not isinstance(loc.value, list):
            return None
        v = loc.value
        if len(v) == 5 and v[0] == 0x03:
            return int.from_bytes(bytes(v[1:]), "little")
        return None

    def names(self) -> list[str]:
        return sorted(self._vars)

    # --- type helpers ---------------------------------------------------
    @staticmethod
    def _type_die(die):
        return die.get_DIE_from_attribute("DW_AT_type") if "DW_AT_type" in die.attributes else None

    def _strip(self, t):
        while t is not None and t.tag in _QUALIFIERS:
            t = self._type_die(t)
        return t

    def _type_name(self, t) -> str:
        while t is not None:
            if "DW_AT_name" in t.attributes:
                return t.attributes["DW_AT_name"].value.decode()
            t = self._type_die(t)
        return "?"

    def _size(self, t) -> int:
        base = self._strip(t)
        if base is None:
            return 0
        if "DW_AT_byte_size" in base.attributes:
            return base.attributes["DW_AT_byte_size"].value
        if base.tag == "DW_TAG_array_type":
            return self._array_len(base) * self._size(self._type_die(base))
        if base.tag == "DW_TAG_pointer_type":
            return 4
        raise SymbolError("cannot determine type size")

    @staticmethod
    def _array_len(arr) -> int:
        for sub in arr.iter_children():
            if sub.tag == "DW_TAG_subrange_type":
                if "DW_AT_count" in sub.attributes:
                    return sub.attributes["DW_AT_count"].value
                if "DW_AT_upper_bound" in sub.attributes:
                    return sub.attributes["DW_AT_upper_bound"].value + 1
        raise SymbolError("array without bound")

    def _kind(self, t) -> str:
        base = self._strip(t)
        if base is None:
            return "bytes"
        if base.tag in _STRUCTS:
            return "struct"
        if base.tag == "DW_TAG_array_type":
            return "array"
        if base.tag == "DW_TAG_pointer_type":
            return "pointer"
        if base.tag == "DW_TAG_enumeration_type":
            return "enum"
        if base.tag == "DW_TAG_base_type":
            enc = base.attributes["DW_AT_encoding"].value
            return {0x02: "bool", 0x04: "float", 0x05: "int", 0x06: "int",
                    0x07: "uint", 0x08: "uint"}.get(enc, "bytes")
        return "bytes"

    # --- public ---------------------------------------------------------
    def _locate(self, path: str):
        tokens = list(_TOKEN.finditer(path))
        if not tokens or "".join(m.group(0) for m in tokens) != path:
            raise SymbolError(f"bad path syntax: {path!r}")
        root = tokens[0].group(1)
        if root is None or root not in self._vars:
            raise SymbolError(f"unknown variable: {root!r}")
        die, addr = self._vars[root]
        t = self._type_die(die)
        for m in tokens[1:]:
            name, idx = m.group(1), m.group(2)
            base = self._strip(t)
            if name is not None:
                if base is None or base.tag not in _STRUCTS:
                    raise SymbolError(f"{path}: '.{name}' on non-struct")
                for member in base.iter_children():
                    if member.tag != "DW_TAG_member" or "DW_AT_name" not in member.attributes:
                        continue
                    if member.attributes["DW_AT_name"].value.decode() != name:
                        continue
                    if "DW_AT_bit_size" in member.attributes:
                        raise SymbolError(f"{path}: bitfield '{name}' not supported")
                    addr += member.attributes["DW_AT_data_member_location"].value
                    t = self._type_die(member)
                    break
                else:
                    raise SymbolError(f"{path}: no member '{name}'")
            else:
                if base is None or base.tag != "DW_TAG_array_type":
                    raise SymbolError(f"{path}: '[{idx}]' on non-array")
                n = self._array_len(base)
                if int(idx) >= n:
                    raise SymbolError(f"{path}: index {idx} out of range ({n})")
                elem = self._type_die(base)
                addr += int(idx) * self._size(elem)
                t = elem
        return t, addr

    def resolve(self, path: str) -> Resolved:
        t, addr = self._locate(path)
        return Resolved(path, addr, self._size(t), self._kind(t), self._type_name(t))

    def members(self, path: str, max_items: int = 256) -> list[Resolved]:
        """One level below `path`: struct members, or array elements (capped). Empty for scalars."""
        t, _ = self._locate(path)
        base = self._strip(t)
        out: list[Resolved] = []
        if base is not None and base.tag in _STRUCTS:
            for m in base.iter_children():
                if m.tag == "DW_TAG_member" and "DW_AT_name" in m.attributes                         and "DW_AT_bit_size" not in m.attributes:
                    try:
                        out.append(self.resolve(f"{path}.{m.attributes['DW_AT_name'].value.decode()}"))
                    except SymbolError:
                        pass
        elif base is not None and base.tag == "DW_TAG_array_type":
            for i in range(min(self._array_len(base), max_items)):
                out.append(self.resolve(f"{path}[{i}]"))
        return out
