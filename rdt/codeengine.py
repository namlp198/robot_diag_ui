"""Code engine: file and build operations on a registered firmware repo, confined to the repo root (decision 0011).

Pure Python, no SDK and no hardware. `claude_bridge` wraps these as MCP tools. Nothing here can run anything except the repo's
configured `build_cmd`, and nothing writes without `Engine.ask` returning True.
"""
from __future__ import annotations

import asyncio
import difflib
import fnmatch
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import firmware as firmware_mod

MAX_READ = 1_000_000           # bytes of one file the engine may read
MAX_WRITE = 1_000_000
MAX_LIST = 300
MAX_HITS = 100
BUILD_TIMEOUT = 600
APPROVAL_TIMEOUT = 600
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "build", "Debug", "Release", ".vscode"}
SECRET_RX = re.compile(r"(^\.env|\.pem$|\.key$|\.pfx$|id_rsa|credentials|secret)", re.I)


class EngineError(Exception):
    pass


def resolve(root: Path, rel: str, *, write: bool = False) -> Path:
    """Real path of `rel` inside `root`. Refuses escapes (.., absolute paths, links), secret-like names, and .git for writes."""
    if not isinstance(rel, str) or "\x00" in rel or len(rel) > 400:
        raise EngineError("bad path")
    root = Path(root).resolve()
    p = (root / rel).resolve() if rel.strip() else root
    if p != root and root not in p.parents:
        raise EngineError(f"{rel}: outside the repository")
    parts = p.relative_to(root).parts
    if any(SECRET_RX.search(x) for x in parts):
        raise EngineError(f"{rel}: secret-like file names are not available")
    if write and ".git" in (x.lower() for x in parts):
        raise EngineError(f"{rel}: .git is not writable")
    return p


def _text(p: Path) -> str:
    if p.stat().st_size > MAX_READ:
        raise EngineError(f"{p.name}: larger than {MAX_READ} bytes")
    data = p.read_bytes()
    if b"\x00" in data[:4096]:
        raise EngineError(f"{p.name}: binary file")
    return data.decode("utf-8", errors="replace")


def list_files(root: Path, rel: str = "", pattern: str = "*") -> dict:
    base = resolve(root, rel)
    if not base.is_dir():
        raise EngineError(f"{rel}: not a directory")
    out, truncated = [], False
    for dp, dn, fn in os.walk(base):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            if fnmatch.fnmatch(f, pattern) and not SECRET_RX.search(f):
                if len(out) >= MAX_LIST:
                    truncated = True
                    break
                out.append(str((Path(dp) / f).relative_to(Path(root).resolve())).replace("\\", "/"))
        if truncated:
            break
    return {"files": out, "truncated": truncated}


def read_file(root: Path, rel: str, start: int = 1, lines: int = 400) -> dict:
    p = resolve(root, rel)
    if not p.is_file():
        raise EngineError(f"{rel}: not a file")
    all_lines = _text(p).splitlines()
    start = max(1, int(start))
    chunk = all_lines[start - 1:start - 1 + max(1, min(int(lines), 2000))]
    return {"path": rel, "start": start, "total_lines": len(all_lines),
            "text": "\n".join(f"{start + i}: {l}" for i, l in enumerate(chunk))}


def search(root: Path, pattern: str, glob: str = "*", rel: str = "") -> dict:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise EngineError(f"bad regex: {e}")
    hits = []
    r = Path(root).resolve()
    for f in list_files(root, rel, glob)["files"]:
        try:
            for n, line in enumerate(_text(r / f).splitlines(), 1):
                if rx.search(line):
                    hits.append({"file": f, "line": n, "text": line.strip()[:200]})
                    if len(hits) >= MAX_HITS:
                        return {"hits": hits, "truncated": True}
        except (EngineError, OSError):
            continue
    return {"hits": hits, "truncated": False}


def plan_edit(root: Path, rel: str, old: str, new: str) -> tuple[Path, str, str]:
    """Returns (path, old content, new content) for replacing exactly one occurrence of `old`. Nothing is written."""
    p = resolve(root, rel, write=True)
    if not p.is_file():
        raise EngineError(f"{rel}: not a file (use repo_write to create one)")
    if not old:
        raise EngineError("old must not be empty")
    cur = _text(p)
    crlf = "\r\n" in cur
    if crlf and "\r\n" not in old:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    n = cur.count(old)
    if n != 1:
        raise EngineError(f"{rel}: `old` matches {n} places, it must match exactly one (add more context)")
    return p, cur, cur.replace(old, new, 1)


def plan_write(root: Path, rel: str, content: str) -> tuple[Path, str, str]:
    p = resolve(root, rel, write=True)
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_WRITE:
        raise EngineError("content too large")
    if p.is_dir():
        raise EngineError(f"{rel}: is a directory")
    return p, (_text(p) if p.is_file() else ""), content


def diff(rel: str, old: str, new: str) -> str:
    d = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=2))
    return d[:6000] + ("\n... (diff cut)" if len(d) > 6000 else "")


def commit(p: Path, content: str):
    """Atomic write (temp file + replace) keeping the text exactly as given."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".rdt-tmp")
    tmp.write_bytes(content.encode("utf-8"))
    os.replace(tmp, p)


def run_build(root: Path, cmd: str | None, timeout: int = BUILD_TIMEOUT) -> dict:
    """Runs the repo's configured build command (a one-liner the user typed in Settings) with the repo as cwd."""
    if not cmd:
        raise EngineError("this repo has no build command: set it in Settings")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(Path(root).resolve()), stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, errors="replace", timeout=timeout)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"(timed out after {timeout} s)\n{(e.stdout or b'').decode('utf-8', 'replace') if isinstance(e.stdout, bytes) else (e.stdout or '')}", -1
    return {"exit_code": code, "seconds": round(time.time() - t0, 1), "output_tail": out[-6000:]}


def check_firmware(root: Path, rel: str) -> dict:
    """The built file the engine wants to register: inside the repo, a real .elf/.hex/.bin."""
    p = resolve(root, rel)
    i = firmware_mod.inspect(p)
    if i.get("error") or i.get("kind") is None:
        raise EngineError(f"{rel}: {i.get('error') or 'not a firmware file'}")
    return {"path": str(p), "kind": i["kind"], "size": i.get("size"), "sha8": i.get("sha8")}


# Engine state shown in the chat. `state_for_tool` maps a tool name to what the engine is doing.
TOOL_STATE = {"repo_list": "reading", "repo_read": "reading", "repo_search": "reading", "repo_edit": "editing",
              "repo_write": "editing", "repo_build": "building", "repo_register_firmware": "registering"}


def state_for_tool(name: str) -> str:
    return TOOL_STATE.get(name.removeprefix("mcp__rdt__"), "thinking")


class Engine:
    """Per-conversation state of the code profile: the repo and the pending approvals."""

    def __init__(self, repo: dict, emit: Callable[[dict], None]):
        self.repo = repo
        self.root = Path(repo["path"]).resolve()
        self._emit = emit
        self.state = "idle"
        self._waiting: dict[str, asyncio.Future] = {}

    def set_state(self, state: str, detail: str = ""):
        self.state = state
        self._emit({"type": "chat", "kind": "engine", "repo": self.repo["name"], "state": state, "detail": detail[:200]})

    async def ask(self, action: str, path: str, diff_text: str) -> bool:
        """Shows the change in the chat and waits for Approve/Deny. Denied on timeout or when the turn is stopped."""
        aid = secrets.token_hex(4)
        fut = asyncio.get_running_loop().create_future()
        self._waiting[aid] = fut
        prev = self.state
        self.set_state("waiting", f"{action} {path}")
        self._emit({"type": "chat", "kind": "approval", "id": aid, "action": action, "path": path, "diff": diff_text})
        try:
            ok = await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            ok = False
        finally:
            self._waiting.pop(aid, None)
        self._emit({"type": "chat", "kind": "approval_done", "id": aid, "allow": bool(ok)})
        self.set_state(prev if prev != "waiting" else "thinking")
        return bool(ok)

    def answer(self, aid: str, allow: bool) -> bool:
        f = self._waiting.get(aid)
        if f is None or f.done():
            return False
        f.set_result(bool(allow))
        return True

    def deny_all(self):
        for f in list(self._waiting.values()):
            if not f.done():
                f.set_result(False)
