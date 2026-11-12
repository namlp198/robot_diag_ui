"""Saved chat conversations: `<root>/<chat_id>/meta.json`, `events.jsonl` (the events the UI replays) and `files/` (the user's attachments).

The UI shows a saved chat by replaying its events through the same reducer it uses live, so what is shown after "open" is what was
shown then. The Claude Code session id is kept in the meta: opening a chat resumes that session when the bundled CLI still has its
transcript (it keeps them in the user's ~/.claude/projects); if it does not, the chat is still readable here.
Streaming text deltas are not stored (the final text event has the full text).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

_ID = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{4}$")
SKIP_KINDS = {"text_delta", "idle"}


class ChatNotFound(KeyError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")  # microseconds: two chats in one second still sort


class ChatStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.RLock()

    def _dir(self, chat_id: str) -> Path:
        if not _ID.match(chat_id or ""):
            raise ChatNotFound(chat_id)
        d = self.root / chat_id
        if not (d / "meta.json").exists():
            raise ChatNotFound(chat_id)
        return d

    def create(self, title: str, model: str = "") -> str:
        with self._lock:
            cid = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
            d = self.root / cid
            (d / "files").mkdir(parents=True)
            self._write_meta(d, {"id": cid, "title": (title.strip().splitlines() or ["(empty)"])[0][:80], "created": _now(), "updated": _now(),
                                 "session_id": None, "model": model, "cost_usd": 0.0, "messages": 0})
            (d / "events.jsonl").touch()
            return cid

    @staticmethod
    def _write_meta(d: Path, meta: dict):
        tmp = d / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, d / "meta.json")

    def meta(self, chat_id: str) -> dict:
        return json.loads((self._dir(chat_id) / "meta.json").read_text(encoding="utf-8"))

    def update(self, chat_id: str, **changes) -> dict:
        with self._lock:
            d = self._dir(chat_id)
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            m.update(changes, updated=_now())
            self._write_meta(d, m)
            return m

    def add_cost(self, chat_id: str, usd: float | None):
        with self._lock:
            m = self.meta(chat_id)
            self.update(chat_id, cost_usd=round(float(usd), 6) if usd is not None else m.get("cost_usd", 0.0))

    def append(self, chat_id: str, event: dict):
        if event.get("kind") in SKIP_KINDS:
            return
        with self._lock:
            d = self._dir(chat_id)
            with open(d / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            if event.get("kind") == "user":
                m = self.meta(chat_id)
                self.update(chat_id, messages=m.get("messages", 0) + 1)

    def events(self, chat_id: str) -> list[dict]:
        p = self._dir(chat_id) / "events.jsonl"
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue                      # a half-written last line must not hide the rest
        return out

    def list(self) -> list[dict]:
        out = []
        if self.root.exists():
            for d in self.root.iterdir():
                try:
                    out.append(self.meta(d.name))
                except (ChatNotFound, OSError, ValueError):
                    continue
        return sorted(out, key=lambda m: m.get("updated", ""), reverse=True)

    def rename(self, chat_id: str, title: str) -> dict:
        title = (title or "").strip()[:80]
        if not title:
            raise ValueError("title is empty")
        return self.update(chat_id, title=title)

    def delete(self, chat_id: str):
        with self._lock:
            shutil.rmtree(self._dir(chat_id))

    def save_file(self, chat_id: str, name: str, data: bytes) -> str:
        """Stores an attachment; returns the stored file name (a counter prefix keeps equal names apart)."""
        with self._lock:
            d = self._dir(chat_id) / "files"
            n = len(list(d.iterdir())) + 1
            stored = f"{n:03d}_{name}"
            (d / stored).write_bytes(data)
            return stored

    def file_path(self, chat_id: str, stored: str) -> Path:
        d = (self._dir(chat_id) / "files").resolve()
        p = (d / stored).resolve()
        if p.parent != d or not p.is_file():
            raise ChatNotFound(stored)
        return p

    def export_markdown(self, chat_id: str) -> str:
        m, lines = self.meta(chat_id), []
        lines += [f"# {m['title']}", "", f"Saved chat {m['id']} · {m['created']} · model {m.get('model') or '?'} · cost ${m.get('cost_usd', 0):.3f}", ""]
        for e in self.events(chat_id):
            k = e.get("kind")
            if k == "user":
                att = "".join(f"\n  - attached: {a['name']} ({a['kind']}, {a['size']} bytes)" for a in e.get("attachments", []))
                lines += ["**You:**", "", e.get("text", "") + att, ""]
            elif k == "text":
                lines += ["**Claude:**", "", e.get("text", ""), ""]
            elif k == "tool_use":
                lines += [f"> tool `{e.get('name')}` {json.dumps(e.get('input'), ensure_ascii=False)[:300]}", ""]
            elif k == "error":
                lines += [f"> error: {e.get('text')}", ""]
        return "\n".join(lines)
