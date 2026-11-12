"""User settings of the daemon (chat model, effort, cost cap, register-read policy), kept in `<sessions>/settings.json`.

Values are validated on load and on save; an unknown or malformed value falls back to the default. The chat reads them when
it starts a conversation, so a change applies to the next conversation.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2", "claude-haiku-5-5"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]  # claude_agent_sdk.EffortLevel; None = the model's default
MODEL_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-\[\]]{2,63}$")


class SettingsError(ValueError):
    pass


@dataclass
class Settings:
    model: str = os.environ.get("RDT_CHAT_MODEL", "claude-sonnet-5-5")
    effort: str | None = None
    max_usd: float = float(os.environ.get("RDT_CHAT_MAX_USD", "2.0"))
    allow_peripheral_reads: bool = False  # live expressions may read peripheral registers (a read can clear flags)
    cube_cli_path: str | None = None      # STM32_Programmer_CLI chosen by the user; None = look for it
    elf_files: dict = field(default_factory=dict)       # target -> [path]: ELF files the user added (symbols / image)
    active_elf: dict = field(default_factory=dict)      # target -> {"symbols": path|None, "image": path|None}: override of targets.yaml
    firmware_files: dict = field(default_factory=dict)  # target -> [{"path", "address"}]: files the flash panel may program

    def to_dict(self) -> dict:
        return asdict(self)


MAX_FILES = 50


def _path(v, what: str) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > 500 or "\x00" in v:
        raise SettingsError(f"{what}: a file path is expected")
    return v


def _targets(d, what: str) -> dict:
    if not isinstance(d, dict):
        raise SettingsError(f"{what} must be an object keyed by board name")
    for k in d:
        if not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", k):
            raise SettingsError(f"{what}: bad board name")
    return d


def validate(d: dict) -> Settings:
    s = Settings()
    if "model" in d:
        if not isinstance(d["model"], str) or not MODEL_RX.match(d["model"]):
            raise SettingsError("model must be a model id such as claude-sonnet-5-5")
        s.model = d["model"]
    if "effort" in d:
        if d["effort"] not in (None, "", *EFFORTS):
            raise SettingsError(f"effort must be one of {EFFORTS} or empty")
        s.effort = d["effort"] or None
    if "max_usd" in d:
        try:
            v = float(d["max_usd"])
        except (TypeError, ValueError):
            raise SettingsError("max_usd must be a number")
        if not 0.05 <= v <= 100:
            raise SettingsError("max_usd must be between 0.05 and 100")
        s.max_usd = v
    if "allow_peripheral_reads" in d:
        if not isinstance(d["allow_peripheral_reads"], bool):
            raise SettingsError("allow_peripheral_reads must be true or false")
        s.allow_peripheral_reads = d["allow_peripheral_reads"]
    if d.get("cube_cli_path") not in (None, ""):
        p = _path(d["cube_cli_path"], "cube_cli_path")
        if Path(p).name.lower() != "stm32_programmer_cli.exe":
            raise SettingsError("cube_cli_path must point to STM32_Programmer_CLI.exe")
        s.cube_cli_path = p
    if "elf_files" in d:
        out = {}
        for t, lst in _targets(d["elf_files"], "elf_files").items():
            if not isinstance(lst, list) or len(lst) > MAX_FILES:
                raise SettingsError(f"elf_files.{t}: a list of at most {MAX_FILES} paths")
            out[t] = list(dict.fromkeys(_path(x, f"elf_files.{t}") for x in lst))
        s.elf_files = out
    if "active_elf" in d:
        out = {}
        for t, v in _targets(d["active_elf"], "active_elf").items():
            if not isinstance(v, dict) or set(v) - {"symbols", "image"}:
                raise SettingsError(f"active_elf.{t}: {{symbols, image}} expected")
            out[t] = {k: (_path(x, f"active_elf.{t}.{k}") if x else None) for k, x in v.items()}
        s.active_elf = out
    if "firmware_files" in d:
        out = {}
        for t, lst in _targets(d["firmware_files"], "firmware_files").items():
            if not isinstance(lst, list) or len(lst) > MAX_FILES:
                raise SettingsError(f"firmware_files.{t}: a list of at most {MAX_FILES} entries")
            items = []
            for e in lst:
                if not isinstance(e, dict) or set(e) - {"path", "address"}:
                    raise SettingsError(f"firmware_files.{t}: {{path, address}} expected")
                addr = e.get("address")
                if addr is not None and (not isinstance(addr, int) or isinstance(addr, bool) or not 0 <= addr <= 0xFFFFFFFF or addr % 4):
                    raise SettingsError(f"firmware_files.{t}: address must be a 32-bit number, multiple of 4")
                items.append({"path": _path(e.get("path"), f"firmware_files.{t}"), "address": addr})
            out[t] = items
        s.firmware_files = out
    return s


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.current = Settings()
        try:
            self.current = validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, SettingsError):
            pass  # missing or damaged file: defaults

    def update(self, changes: dict) -> Settings:
        merged = {**self.current.to_dict(), **changes}
        new = validate(merged)  # raises before anything is stored
        self.current = new
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(new.to_dict(), indent=2), encoding="utf-8")
        return new
