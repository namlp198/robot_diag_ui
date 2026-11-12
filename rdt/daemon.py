"""rdt daemon: owns the probes, serves live samples to UI and tools (read-only toward the hardware).

HTTP + WebSocket on 127.0.0.1 only. No endpoint writes target memory, halts or resets a core.
Host and Origin headers must be local (guards against DNS-rebinding from a web page).
"""
from __future__ import annotations

import asyncio
import copy
import sys
import threading
from contextlib import asynccontextmanager
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import paths as paths_mod
from .cli import ROOT, elf_paths, load_targets, open_symbols
from . import (analyzers, cantap as cantap_mod, cubecli as cubecli_mod, envcheck as envcheck_mod, firmware as firmware_mod, exprs as exprs_mod, flash as flash_mod, rcl as rcl_mod,
               reference as reference_mod, settings as settings_mod, sweep as sweep_mod)
from .recorder import Recorder, list_sessions, open_session
from .sampler import Sampler
from .symbols import SymbolError, SymbolTable
from .vcp import VcpError, VcpReader

RING = 4000  # samples kept per target for late-joining clients
# Newest modification time (whole seconds) of the daemon's own code when it started: scripts/start.ps1 compares it with the
# files on disk and restarts a daemon that is older than the code (a stale daemon serves a new UI with old endpoints).
CODE_STAMP = int(max([p.stat().st_mtime for p in Path(__file__).parent.glob("*.py")] or [Path(sys.executable).stat().st_mtime]))  # installed app: the exe
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def _host_only(h: str) -> str:
    h = h.strip()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


class WatchRequest(BaseModel):
    watches: dict[str, list[str]] = Field(description="target -> variable paths")
    hz: float = Field(10.0, gt=0, le=200)
    vcp: list[str] = []


class FlashRequest(BaseModel):
    target: str
    image: str
    address: int | None = None   # start address of a .bin (default: the registered one, else the start of the board's flash)
    confirm: str = ""
    motors_safe: bool = False


class CubeRequest(BaseModel):
    command: str
    target: str = ""
    address: str | int | None = None
    size: str | int | None = None
    dry_run: bool = False


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    view: dict | None = None


class RecordRequest(BaseModel):
    label: str = Field("", pattern=r"^[A-Za-z0-9_-]{0,40}$")


class Hub:
    def __init__(self, sessions_dir: Path | None = None):
        self.base_targets = load_targets()      # targets.yaml as written
        self.targets = copy.deepcopy(self.base_targets)  # with the ELF choices of Settings applied (apply_settings)
        self.sessions_dir = sessions_dir or ROOT / "sessions"
        self.lock = threading.RLock()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subs: set[asyncio.Queue] = set()
        self.samplers: list[Sampler] = []
        self.readers: list[VcpReader] = []
        self.ring: dict[str, deque] = {}
        self.logs: dict[str, deque] = {}
        self.columns: dict[str, list[str]] = {}
        self.errors: deque = deque(maxlen=50)
        self.recorder: Recorder | None = None
        self.t0 = time.perf_counter()
        self.running = False
        self.flashing = False
        self.findings: dict[tuple, dict] = {}  # live findings seen so far, keyed to avoid repeats
        self.chat = None  # ChatSession, created on first use (needs claude_agent_sdk)
        self.box = None
        self.settings = settings_mod.Store(self.sessions_dir / "settings.json")
        self.apply_settings()
        self.exprs: dict[str, list] = {}          # live expressions per target (rdt.exprs.Expr)
        self.expr_specs: dict[str, list] = {}     # as sent by the UI (including refused ones)
        self.expr_info: dict[str, list] = {}      # resolved info or error per spec
        self.expr_latest: dict[str, dict] = {}    # target -> {"t": ..., "values": {id: value}}
        self.frames: deque = deque(maxlen=600)    # decoded RCL frames seen in the boards' buffers (rdt.rcl)
        self.capture: rcl_mod.FrameCapture | None = None
        self.can: deque = deque(maxlen=1500)      # sampled CAN frames (rdt.cantap), newest last
        self.can_stats: dict[str, dict] = {}      # target -> tap statistics

    def apply_settings(self):
        """Settings that change what the daemon uses: the ELF files per board and the STM32_Programmer_CLI path. Takes effect at
        the next "Start reading" (samplers resolve symbols when they are created)."""
        s = self.settings.current
        targets = copy.deepcopy(self.base_targets)
        for name, pick in s.active_elf.items():
            if name in targets:
                if pick.get("symbols") and Path(pick["symbols"]).is_file():
                    targets[name]["elf"] = str(Path(pick["symbols"]))
                if pick.get("image") and Path(pick["image"]).is_file():
                    targets[name]["image_elf"] = str(Path(pick["image"]))
        self.targets = targets
        cli = Path(s.cube_cli_path) if s.cube_cli_path else None
        if cli is None or not cli.is_file():
            found = envcheck_mod.cube_candidates(None)
            cli = found[0][0] if found else flash_mod.CUBE_CLI
        flash_mod.CUBE_CLI = cli

    def registered_firmware(self, target: str) -> list[tuple[Path, int | None]]:
        """Firmware files the user registered for `target` in Settings: (resolved path, .bin address)."""
        out = []
        for e in self.settings.current.firmware_files.get(target, []):
            try:
                out.append((Path(e["path"]).resolve(), e.get("address")))
            except OSError:
                pass
        return out

    # --- fan-out (called from sampler threads) -------------------------------------------------
    def _publish(self, msg: dict):
        loop = self.loop
        if loop is None:
            return
        for q in list(self.subs):
            loop.call_soon_threadsafe(self._offer, q, msg)

    @staticmethod
    def _offer(q: asyncio.Queue, msg: dict):
        if q.full():
            try:
                q.get_nowait()  # slow client: drop oldest
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(msg)

    def on_sample(self, target: str, t: float, vals: list):
        with self.lock:
            self.ring[target].append((t, vals))
            if self.recorder:
                self.recorder.add_sample(target, t, vals)
        self._publish({"type": "sample", "target": target, "t": round(t, 6), "values": vals})
        cap = self.capture
        if cap is not None:
            for fr in cap.feed(target, t, vals):
                with self.lock:
                    self.frames.append(fr)
                self._publish({"type": "frame", **fr})

    def on_can(self, target: str, t: float, frames: list[dict], stats: dict):
        """CAN frames sampled by rdt.cantap. The message carries `frames` and `stats` (no frame field named `type`)."""
        stamped = [{**f, "t": round(t, 6), "target": target} for f in frames]
        with self.lock:
            self.can_stats[target] = stats
            for f in stamped:
                self.can.append(f)
                if self.recorder:
                    self.recorder.add_can(target, t, {k: v for k, v in f.items() if k not in ("t", "target")})
        if stamped or stats.get("polls", 0) % 10 == 1:  # stats at least every 10th poll
            self._publish({"type": "can", "target": target, "frames": stamped, "stats": stats})

    def on_expr(self, target: str, t: float, values: dict):
        with self.lock:
            self.expr_latest[target] = {"t": round(t, 6), "values": values}
        self._publish({"type": "expr", "target": target, "t": round(t, 6), "values": values})

    def set_exprs(self, target: str, specs: list[dict]) -> list[dict]:
        """Replace the live expressions of `target`. Returns one info dict per spec (with `error` for refused ones)."""
        if target not in self.targets:
            raise HTTPException(404, "unknown target")
        if len(specs) > exprs_mod.MAX_EXPRS:
            raise HTTPException(400, f"at most {exprs_mod.MAX_EXPRS} expressions per target")
        cfg = self.targets[target]
        allow = self.settings.current.allow_peripheral_reads
        st = None
        if any(not exprs_mod._NUM.match(str(s.get("text", "")).strip()) for s in specs):
            try:
                st = open_symbols(cfg)
            except (SymbolError, OSError):
                st = None
        built, info = [], []
        try:
            for s in specs:
                try:
                    e = exprs_mod.build(target, cfg, s, st, allow)
                    built.append(e)
                    info.append(e.info())
                except exprs_mod.ExprError as err:
                    info.append({"id": str(s.get("id", "")), "text": str(s.get("text", "")), "error": str(err)})
        finally:
            if st is not None:
                st.close()
        with self.lock:
            self.exprs[target] = built
            self.expr_specs[target] = [dict(s) for s in specs]   # kept so a policy change can re-check refused ones
            self.expr_info[target] = info
            self.expr_latest.pop(target, None)
            for sm in self.samplers:
                if sm.target == target:
                    sm.set_exprs(built)
        return info

    def on_log(self, target: str, t: float, line: str):
        with self.lock:
            self.logs[target].append((t, line))
            if self.recorder:
                self.recorder.add_log(target, t, line)
        self._publish({"type": "log", "target": target, "t": round(t, 6), "line": line})

    def on_error(self, target: str, msg: str):
        t = time.perf_counter() - self.t0
        with self.lock:
            self.errors.append({"t": round(t, 3), "target": target, "text": msg})
            if self.recorder:
                self.recorder.add_event(t, f"error:{target}", msg)
        self._publish({"type": "error", "target": target, "t": round(t, 6), "text": msg})

    # --- control ---------------------------------------------------------------------------------
    def start(self, req: WatchRequest):
        with self.lock:
            if self.flashing:
                raise HTTPException(409, "a flash is in progress")
            if self.running:
                raise HTTPException(409, "already running; POST /api/stop first")
            for name in [*req.watches, *req.vcp]:
                if name not in self.targets:
                    raise HTTPException(400, f"unknown target {name!r}")
            samplers, readers = [], []
            t0 = time.perf_counter()
            try:
                for name, paths in req.watches.items():
                    t = self.targets[name]
                    elf, image = elf_paths(t)
                    samplers.append(Sampler(name, t["probe_serial"], elf, paths, req.hz, self.on_sample, t0,
                                            self.on_error, image=image))
                for name in req.vcp:
                    readers.append(VcpReader(name, self.targets[name], self.on_log, t0, self.on_error))
            except FileNotFoundError as e:
                raise HTTPException(400, f"ELF file not found: {e.filename} - choose the ELF in Settings > ELF files")
            except (SymbolError, VcpError, OSError) as e:
                raise HTTPException(400, str(e))
            self.can.clear()
            self.can_stats = {}
            for sm in samplers:
                sm.expr_sink = self.on_expr
                sm.set_exprs(self.exprs.get(sm.target, []))
                try:  # CAN frame tap for targets whose firmware has an FDCAN1 handle (the robot)
                    st = open_symbols(self.targets[sm.target])
                    try:
                        tap = cantap_mod.build(self.targets[sm.target], st, self.settings.current.allow_peripheral_reads)
                    finally:
                        st.close()
                    if tap is not None:
                        sm.set_tap(tap, self.on_can)
                except (SymbolError, OSError):
                    pass
            self.t0 = t0
            self.samplers, self.readers = samplers, readers
            self.ring = {s.target: deque(maxlen=RING) for s in samplers}
            self.logs = {r.target: deque(maxlen=RING) for r in readers}
            self.columns = {s.target: s.paths for s in samplers}
            self.capture = rcl_mod.FrameCapture(self.columns)
            self.frames.clear()
            self.expr_latest = {}
            self.findings = {}
            self.running = True
            for x in [*samplers, *readers]:
                x.start()

    def stop(self):
        with self.lock:
            xs = [*self.samplers, *self.readers]
            self.running = False
        for x in xs:
            x.stop()
        for x in xs:
            x.join(timeout=3)
        self.stop_record()

    def start_record(self, label: str) -> Path:
        with self.lock:
            if not self.running:
                raise HTTPException(409, "not running")
            if self.recorder:
                raise HTTPException(409, "already recording")
            info = {s.target: {"serial": s.serial, "elf": str(s.image),
                               "paths": s.paths, "vars": s.vars} for s in self.samplers}
            self.sessions_dir.mkdir(exist_ok=True)
            self.recorder = Recorder(self.sessions_dir, info, label=label)
            return self.recorder.dir

    def stop_record(self) -> str | None:
        with self.lock:
            rec, self.recorder = self.recorder, None
        if rec:
            rec.close()
            return rec.dir.name
        return None

    def analyze_live(self, last_s: float = 120.0) -> dict:
        res = analyzers.analyze(analyzers.from_hub(self, last_s))
        fresh = []
        with self.lock:
            for f in res["findings"]:
                key = (f["id"], f["target"], round(f["t0"], 1))
                if key not in self.findings:
                    self.findings[key] = f
                    fresh.append(f)
        for f in fresh:
            self._publish({"type": "finding", **f})
        return res

    def status(self) -> dict:
        with self.lock:
            return {
                "code_stamp": CODE_STAMP,
                "running": self.running, "recording": self.recorder.dir.name if self.recorder else None,
                "t_now": round(time.perf_counter() - self.t0, 3),
                "targets": {n: {"mcu": t.get("mcu"), "probe_serial": t["probe_serial"],
                                "has_vcp": bool(t.get("log_port"))} for n, t in self.targets.items()},
                "watches": {s.target: {"paths": s.paths, "hz": s.hz, "reads": s.reads, "failures": s.failures,
                                       "alive": s.is_alive(),
                                       "fw": None if s.fw is None else {"ok": s.fw.ok, "text": s.fw.summary()}} for s in self.samplers},
                "vcp": {r.target: {"port": r.port, "lines": r.lines, "alive": r.is_alive()} for r in self.readers},
                "errors": list(self.errors)[-10:],
            }


def create_app(hub: Hub | None = None) -> FastAPI:
    hub = hub or Hub()
    @asynccontextmanager
    async def lifespan(_app):
        hub.loop = asyncio.get_running_loop()

        async def analyze_loop():
            while True:
                await asyncio.sleep(2.0)
                if hub.running and hub.ring:
                    try:
                        await asyncio.to_thread(hub.analyze_live)
                    except Exception as e:  # an analyzer bug must not stop the daemon
                        hub.on_error("daemon", f"analyzer failed: {e}")

        task = asyncio.create_task(analyze_loop())
        yield
        task.cancel()
        if hub.chat is not None:
            await hub.chat.close()
        hub.stop()

    app = FastAPI(title="rdt daemon", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.hub = hub

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = _host_only(request.headers.get("host", ""))
        origin = request.headers.get("origin")
        if host not in LOCAL_HOSTS or (origin and _host_only(origin.split("://", 1)[-1]) not in LOCAL_HOSTS):
            return JSONResponse({"detail": "local access only"}, status_code=403)
        return await call_next(request)

    def get_chat():
        if hub.chat is None:
            try:
                from .agent_tools import ToolBox
                from .claude_bridge import ChatSession
            except ImportError as e:
                raise HTTPException(501, f"chat needs claude-agent-sdk: pip install -e .[chat] ({e})")
            hub.box = ToolBox(hub, ui=lambda m: hub._publish({"type": "ui", **m}))
            hub.chat = ChatSession(hub.box, emit=hub._publish, settings=hub.settings)
        return hub.chat

    auth_cache: dict = {"t": 0.0, "v": None}

    def auth_status(fresh: bool = False) -> dict:
        """Login state of the Claude Code bundled with the SDK (`claude auth status`), cached for 30 s unless `fresh`."""
        now = time.time()
        if not fresh and auth_cache["v"] is not None and now - auth_cache["t"] < 30:
            return auth_cache["v"]
        v = envcheck_mod.claude_status()
        auth_cache.update(t=now, v=v)
        return v
    @app.get("/api/chat/info")
    async def chat_info():
        """Is the chat usable (SDK installed, logged in) and with which settings. No model name is shown in the UI by default."""
        a = await asyncio.to_thread(auth_status, False)
        return {**a, "busy": bool(hub.chat and hub.chat.busy), "settings": hub.settings.current.to_dict()}

    @app.get("/api/settings")
    def get_settings():
        return {"settings": hub.settings.current.to_dict(), "models": settings_mod.MODELS, "efforts": settings_mod.EFFORTS,
                "core_registers": [{"name": n, "address": a, "type": t, "meaning": m} for n, a, t, m in exprs_mod.CORE_REGISTERS],
                "targets": {n: {"mcu": t.get("mcu"), "flash_range": t.get("flash_range"),
                                "elf": str((ROOT / t["elf"]).resolve()),
                                "image_elf": str((ROOT / t["image_elf"]).resolve()) if t.get("image_elf") else None}
                            for n, t in hub.base_targets.items()}}

    def _check_file_settings(changes: dict):
        """Everything the user adds in Settings is looked at before it is stored: board names, files that exist and what they are."""
        for key in ("elf_files", "active_elf", "firmware_files"):
            if key in changes and isinstance(changes[key], dict):
                for t in changes[key]:
                    if t not in hub.targets:
                        raise HTTPException(400, f"{key}: unknown board {t!r}")
        for t, lst in (changes.get("elf_files") or {}).items():
            for p in lst:
                i = firmware_mod.inspect(p)
                if i.get("error") or i.get("kind") != "elf":
                    raise HTTPException(400, f"{p}: {i.get('error') or 'not an ELF file'}")
        for t, pick in (changes.get("active_elf") or {}).items():
            for role, p in pick.items():
                if p:
                    i = firmware_mod.inspect(p)
                    if i.get("error") or i.get("kind") != "elf":
                        raise HTTPException(400, f"{p}: {i.get('error') or 'not an ELF file'}")
                    if role == "symbols" and not i.get("dwarf"):
                        raise HTTPException(400, f"{p}: no DWARF debug info, so it cannot name variables (use it as the image ELF instead)")
        for t, lst in (changes.get("firmware_files") or {}).items():
            for e in lst:
                i = firmware_mod.inspect(e.get("path", ""))
                if i.get("error") or i.get("kind") is None:
                    raise HTTPException(400, f"{e.get('path')}: {i.get('error') or 'not a firmware file'}")
        cp = changes.get("cube_cli_path")
        if cp and envcheck_mod.cube_version(Path(cp)) is None:
            raise HTTPException(400, f"{cp}: not a working STM32_Programmer_CLI")

    @app.put("/api/settings")
    async def put_settings(changes: dict):
        await asyncio.to_thread(_check_file_settings, changes)
        try:
            new = hub.settings.update(changes)
        except settings_mod.SettingsError as e:
            raise HTTPException(400, str(e))
        hub.apply_settings()
        applied = False
        if hub.chat is not None and not hub.chat.busy:  # next question starts a fresh conversation with the new settings
            await hub.chat.close()
            hub.chat = None
            applied = True
        if "allow_peripheral_reads" in changes:  # re-check the expressions against the new policy
            for tgt, specs in list(hub.expr_specs.items()):
                hub.set_exprs(tgt, specs)
        return {"settings": new.to_dict(), "chat_restarted": applied}

    @app.get("/api/env/cube")
    async def env_cube():
        return await asyncio.to_thread(envcheck_mod.cube_status, hub.settings.current.cube_cli_path)

    @app.get("/api/env/stlink")
    async def env_stlink():
        serials = {t["probe_serial"]: n for n, t in hub.targets.items()}
        return await asyncio.to_thread(envcheck_mod.scan_stlink, serials)

    @app.get("/api/env/claude")
    async def env_claude(fresh: bool = False):
        return await asyncio.to_thread(auth_status, fresh)

    @app.post("/api/env/claude/login")
    async def env_claude_login():
        """Opens `claude auth login` of the bundled Claude Code in its own console (the browser login happens there)."""
        r = await asyncio.to_thread(envcheck_mod.start_claude_login)
        if not r["started"]:
            raise HTTPException(501, r["error"])
        auth_cache["v"] = None
        return r

    @app.post("/api/dialog/open")
    async def dialog_open(body: dict):
        """Native file picker on the machine the daemon runs on (this is a local tool). Returns the chosen path or null."""
        return await asyncio.to_thread(envcheck_mod.pick_file, str(body.get("kind", "")), body.get("initial"))

    @app.post("/api/firmware/inspect")
    async def firmware_inspect(body: dict):
        return await asyncio.to_thread(firmware_mod.inspect, str(body.get("path", "")))

    @app.get("/api/can")
    def can_frames(limit: int = 300):
        """Sampled CAN/FDCAN frames of the robot (rdt.cantap) and the tap statistics. Sampled, not a bus capture."""
        with hub.lock:
            return {"frames": list(hub.can)[-min(limit, 1500):], "stats": dict(hub.can_stats)}

    @app.get("/api/sessions/{name}/can")
    def session_can(name: str):
        p = hub.sessions_dir / name
        if "/" in name or "\\" in name or ".." in name or not (p / "meta.json").exists():
            raise HTTPException(404, "no such session")
        s = open_session(p)
        out = []
        for tgt in s.targets:
            out += [{**f, "target": tgt} for f in s.can(tgt)]
        out.sort(key=lambda f: f["t"])
        return {"frames": out[-1500:]}

    @app.get("/api/frames")
    def frames(limit: int = 200, source: str = ""):
        with hub.lock:
            rows = [f for f in hub.frames if not source or f["source"] == source][-min(limit, 600):]
        return {"frames": rows, "sources": rcl_mod.SOURCES}

    @app.get("/api/sessions/{name}/frames")
    def session_frames(name: str, limit: int = 600):
        p = hub.sessions_dir / name
        if "/" in name or "\\" in name or ".." in name or not (p / "meta.json").exists():
            raise HTTPException(404, "no such session")
        s = open_session(p)
        cols = {}
        data = {}
        for tgt in s.targets:
            try:
                cols[tgt], data[tgt] = s.samples(tgt)
            except OSError:
                continue
        cap = rcl_mod.FrameCapture({t: c[1:] for t, c in cols.items()})
        out = []
        for tgt, rows in data.items():
            for row in rows:
                out += cap.feed(tgt, row[0], row[1:])
        out.sort(key=lambda f: f["t"])
        return {"frames": out[-min(limit, 2000):], "sources": rcl_mod.SOURCES}

    @app.get("/api/expr")
    def get_exprs():
        with hub.lock:
            return {"items": {t: list(i) for t, i in hub.expr_info.items()}, "latest": dict(hub.expr_latest),
                    "allow_peripheral_reads": hub.settings.current.allow_peripheral_reads}

    @app.put("/api/expr")
    def put_exprs(body: dict):
        target = str(body.get("target", ""))
        items = body.get("items", [])
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise HTTPException(400, "items must be a list of objects")
        return {"items": hub.set_exprs(target, items)}

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        c = get_chat()
        try:
            c.start_turn(req.text, req.view)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/chat/stop")
    async def chat_stop():
        if hub.chat is not None:
            await hub.chat.interrupt()
        return {"ok": True}

    @app.post("/api/chat/reset")
    async def chat_reset():
        if hub.chat is not None:
            await hub.chat.close()
            hub.chat = None
        return {"ok": True}

    @app.get("/api/status")
    def status():
        return hub.status()

    @app.post("/api/watch")
    def watch(req: WatchRequest):
        hub.start(req)
        return hub.status()

    @app.post("/api/stop")
    def stop():
        hub.stop()
        return hub.status()

    @app.post("/api/record/start")
    def record_start(req: RecordRequest):
        return {"session": hub.start_record(req.label).name}

    @app.post("/api/record/stop")
    def record_stop():
        return {"session": hub.stop_record()}

    @app.get("/api/samples")
    def samples(target: str, since: float = 0.0, limit: int = 2000):
        with hub.lock:
            if target not in hub.ring:
                raise HTTPException(404, f"{target!r} is not being watched")
            rows = [[round(t, 6), *v] for t, v in hub.ring[target] if t > since][-limit:]
            return {"columns": ["t_s", *hub.columns[target]], "rows": rows}

    @app.get("/api/log")
    def log(target: str, since: float = 0.0, limit: int = 500):
        with hub.lock:
            if target not in hub.logs:
                raise HTTPException(404, f"no VCP log for {target!r}")
            return [{"t": round(t, 6), "line": line} for t, line in hub.logs[target] if t > since][-limit:]

    @app.get("/api/symbols")
    def symbols(target: str, q: str = "", limit: int = 50):
        if target not in hub.targets:
            raise HTTPException(404, "unknown target")
        st = open_symbols(hub.targets[target])
        try:
            names = [n for n in st.names() if q.lower() in n.lower()][:limit]
            out = []
            for n in names:
                r = st.resolve(n)
                out.append({"path": r.path, "address": r.address, "size": r.size, "kind": r.kind,
                            "type": r.type_name})
            return out
        finally:
            st.close()

    @app.get("/api/resolve")
    def resolve(target: str, path: str):
        if target not in hub.targets:
            raise HTTPException(404, "unknown target")
        st = open_symbols(hub.targets[target])
        try:
            r = st.resolve(path)
        except SymbolError as e:
            raise HTTPException(400, str(e))
        finally:
            st.close()
        return {"path": r.path, "address": r.address, "size": r.size, "kind": r.kind, "type": r.type_name}

    @app.get("/api/findings")
    def findings(last_s: float = 120.0):
        if not hub.ring:
            raise HTTPException(409, "not running")
        return hub.analyze_live(last_s)

    @app.get("/api/sessions/{name}/findings")
    def session_findings(name: str):
        p = hub.sessions_dir / name
        if "/" in name or "\\" in name or ".." in name or not (p / "meta.json").exists():
            raise HTTPException(404, "no such session")
        return analyzers.analyze(analyzers.from_session(open_session(p)))

    def _flash_inputs(req: FlashRequest):
        if req.target not in hub.targets:
            raise HTTPException(404, "unknown target")
        cfg = hub.targets[req.target]
        img = Path(req.image)
        img = (img if img.is_absolute() else ROOT / img).resolve()
        if not img.is_relative_to(ROOT.parent) and img not in [p for p, _a in hub.registered_firmware(req.target)]:
            raise HTTPException(400, "image must be inside the workspace repositories folder or registered for this board in Settings")
        return cfg, img

    def _flash_plan(req: FlashRequest):
        from .backend import BackendError, Probe, list_serials
        cfg, img = _flash_inputs(req)
        if hub.running or hub.flashing:
            raise HTTPException(409, "stop reading first: flashing needs the probe exclusively")
        probe = None
        try:
            probe = Probe(cfg["probe_serial"]).open()
            read = probe.read
        except BackendError:
            read = None
        try:
            reg = hub.registered_firmware(req.target)
            addr = req.address if req.address is not None else next((a for p, a in reg if p == img), None)
            return flash_mod.plan(req.target, cfg, img, ROOT, read,
                                  lambda s: s in list_serials() or probe is not None,
                                  extra_allowed=[p for p, _a in reg], address=addr), cfg
        except flash_mod.FlashError as e:
            raise HTTPException(400, str(e))
        finally:
            if probe is not None:
                probe.close()

    @app.get("/api/flash/candidates")
    def flash_candidates():
        """ELF files that match each target's allowed_images (the only images the plan will accept)."""
        import glob
        import os as _os
        out = {}
        for name, cfg in hub.targets.items():
            files = []
            for g in cfg.get("allowed_images", []):
                files += glob.glob(_os.path.normpath(str(ROOT / g)))
            files += [str(p) for p, _a in hub.registered_firmware(name)]
            out[name] = sorted(set(str(Path(f).resolve()) for f in files))
        return out

    @app.get("/api/flash/files")
    def flash_files():
        """Per board: the files the Flash panel offers, with kind, address (.bin) and where the entry comes from."""
        import glob
        import os as _os
        out = {}
        for name, cfg in hub.targets.items():
            seen, rows = set(), []
            for p, a in hub.registered_firmware(name):
                seen.add(str(p))
                rows.append({"path": str(p), "kind": firmware_mod.kind_of(p), "address": a, "source": "settings"})
            for g in cfg.get("allowed_images", []):
                for f in glob.glob(_os.path.normpath(str(ROOT / g))):
                    f = str(Path(f).resolve())
                    if f not in seen:
                        seen.add(f)
                        rows.append({"path": f, "kind": "elf", "address": None, "source": "targets.yaml"})
            out[name] = sorted(rows, key=lambda r: r["path"].lower())
        return out

    @app.post("/api/flash/plan")
    def flash_plan(req: FlashRequest):
        """Read-only dry run: checks and the exact command. Nothing is written."""
        p, _cfg = _flash_plan(req)
        return p.to_dict()

    @app.post("/api/flash/run")
    def flash_run(req: FlashRequest):
        """Programs the board. Needs the plan's confirm phrase (+ motors_safe for the robot) and a stopped daemon."""
        from .backend import Probe
        p, cfg = _flash_plan(req)
        hub.flashing = True
        try:
            return flash_mod.run(p, cfg, req.confirm, req.motors_safe, ROOT, hub.sessions_dir,
                                 read_after=lambda: Probe(cfg["probe_serial"]))
        except flash_mod.FlashError as e:
            raise HTTPException(400, str(e))
        finally:
            hub.flashing = False

    @app.get("/api/reference")
    def reference_data():
        """Bilingual reference: monitored variables, pyOCD and STM32_Programmer_CLI commands (rdt.reference)."""
        return reference_mod.REFERENCE

    @app.post("/api/cube/run")
    def cube_run(req: CubeRequest):
        """Read-only STM32_Programmer_CLI commands (whitelist in rdt.cubecli). Needs the probe free (watch stopped)."""
        cfg = None
        if req.command != "list":
            if req.target not in hub.targets:
                raise HTTPException(404, "unknown target")
            cfg = hub.targets[req.target]
        if hub.running or hub.flashing:
            raise HTTPException(409, "stop reading first: the CLI needs the probe exclusively")
        try:
            args = cubecli_mod.build(req.command, cfg, req.address, req.size)
            if req.dry_run:
                return {"command": args, "returncode": None, "output": ""}
            hub.flashing = True  # blocks /api/watch while the CLI holds the probe
            try:
                return cubecli_mod.run(args)
            finally:
                hub.flashing = False
        except cubecli_mod.CubeCliError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/sweep")
    def sweep_live():
        if not hub.ring:
            raise HTTPException(409, "not running")
        return sweep_mod.compute(analyzers.from_hub(hub))

    @app.get("/api/sessions/{name}/sweep")
    def sweep_session(name: str, csv: bool = False):
        p = hub.sessions_dir / name
        if "/" in name or "\\" in name or ".." in name or not (p / "meta.json").exists():
            raise HTTPException(404, "no such session")
        res = sweep_mod.compute(analyzers.from_session(open_session(p)))
        if csv:
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(sweep_mod.to_csv(res["rows"]), media_type="text/csv")
        return res

    @app.get("/api/members")
    def members(target: str, path: str, limit: int = 256):
        if target not in hub.targets:
            raise HTTPException(404, "unknown target")
        st = open_symbols(hub.targets[target])
        try:
            return [{"path": r.path, "address": r.address, "size": r.size, "kind": r.kind, "type": r.type_name}
                    for r in st.members(path, limit)]
        except SymbolError as e:
            raise HTTPException(400, str(e))
        finally:
            st.close()

    @app.get("/api/sessions")
    def sessions():
        return [p.name for p in list_sessions(hub.sessions_dir)]

    @app.get("/api/sessions/{name}")
    def session(name: str, target: str | None = None, limit: int = 5000):
        p = hub.sessions_dir / name
        if "/" in name or "\\" in name or ".." in name or not (p / "meta.json").exists():
            raise HTTPException(404, "no such session")
        s = open_session(p)
        out = {"meta": s.meta, "events": s.events()[:200]}
        if target:
            if target not in s.targets:
                raise HTTPException(404, "target not in session")
            cols, rows = s.samples(target)
            out["columns"], out["rows"] = cols, rows[-limit:]
            out["log"] = s.logs(target)[-limit:]
        return out

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        origin = sock.headers.get("origin")
        if _host_only(sock.headers.get("host", "")) not in LOCAL_HOSTS or (
                origin and _host_only(origin.split("://", 1)[-1]) not in LOCAL_HOSTS):
            await sock.close(code=1008)
            return
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        hub.subs.add(q)
        try:
            await sock.send_json({"type": "hello", "status": hub.status()})
            while True:
                await sock.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            hub.subs.discard(q)

    dist = paths_mod.UI_DIST
    if dist.is_dir():  # built UI (npm run build in ui/); API and /ws routes above take precedence
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def serve(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("rdt serve binds to loopback only")
    uvicorn.run(create_app(), host=host, port=port, log_level="info", log_config=None if sys.stdout is None else uvicorn.config.LOGGING_CONFIG)
