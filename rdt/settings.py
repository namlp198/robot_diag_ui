"""User settings of the daemon (chat model, effort, cost cap, register-read policy), kept in `<sessions>/settings.json`.

Values are validated on load and on save; an unknown or malformed value falls back to the default. The chat reads them when
it starts a conversation, so a change applies to the next conversation.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
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

    def to_dict(self) -> dict:
        return asdict(self)


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
