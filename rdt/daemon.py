"""rdt daemon: owns the probes, serves live samples to UI and tools (read-only toward the hardware).

HTTP + WebSocket on 127.0.0.1 only. No endpoint writes target memory, halts or resets a core.
Host and Origin headers must be local (guards against DNS-rebinding from a web page).
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .cli import ROOT, elf_paths, load_targets, open_symbols
from . import (analyzers, cubecli as cubecli_mod, exprs as exprs_mod, flash as flash_mod, rcl as rcl_mod,
               reference as reference_mod, settings as settings_mod, sweep as sweep_mod)
from .recorder import Recorder, list_sessions, open_session
from .sampler import Sampler
from .symbols import SymbolError, SymbolTable
from .vcp import VcpError, VcpReader

RING = 4000  # samples kept per target for late-joining clients
# Newest modification time (whole seconds) of the daemon's own code when it started: scripts/start.ps1 compares it with the
# files on disk and restarts a daemon that is older than the code (a stale daemon serves a new UI with old endpoints).
CODE_STAMP = int(max(p.stat().st_mtime for p in Path(__file__).parent.glob("*.py")))
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
        self.targets = load_targets()
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
        self.exprs: dict[str, list] = {}          # live expressions per target (rdt.exprs.Expr)
        self.expr_specs: dict[str, list] = {}     # as sent by the UI (including refused ones)
        self.expr_info: dict[str, list] = {}      # resolved info or error per spec
        self.expr_latest: dict[str, dict] = {}    # target -> {"t": ..., "values": {id: value}}
        self.frames: deque = deque(maxlen=600)    # decoded RCL frames seen in the boards' buffers (rdt.rcl)
        self.capture: rcl_mod.FrameCapture | None = None

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
            except (SymbolError, VcpError, OSError) as e:
                raise HTTPException(400, str(e))
            for sm in samplers:
                sm.expr_sink = self.on_expr
                sm.set_exprs(self.exprs.get(sm.target, []))
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

    def auth_status() -> dict:
        """Login state of the Claude Code bundled with the SDK (`claude auth status`), cached for 30 s."""
        import json as _json
        import subprocess
        now = time.time()
        if auth_cache["v"] is not None and now - auth_cache["t"] < 30:
            return auth_cache["v"]
        try:
            import claude_agent_sdk
        except ImportError:
            v = {"sdk": False, "logged_in": None}
        else:
            exe = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
            v = {"sdk": True, "logged_in": None}
            if exe.exists():
                try:
                    r = subprocess.run([str(exe), "auth", "status"], capture_output=True, text=True, timeout=15)
                    v["logged_in"] = bool(_json.loads(r.stdout).get("loggedIn"))
                except Exception:
                    v["logged_in"] = None
        auth_cache.update(t=now, v=v)
        return v

    @app.get("/api/chat/info")
    async def chat_info():
        """Is the chat usable (SDK installed, logged in) and with which settings. No model name is shown in the UI by default."""
        a = await asyncio.to_thread(auth_status)
        return {**a, "busy": bool(hub.chat and hub.chat.busy), "settings": hub.settings.current.to_dict()}

    @app.get("/api/settings")
    def get_settings():
        return {"settings": hub.settings.current.to_dict(), "models": settings_mod.MODELS, "efforts": settings_mod.EFFORTS,
                "core_registers": [{"name": n, "address": a, "type": t, "meaning": m} for n, a, t, m in exprs_mod.CORE_REGISTERS]}

    @app.put("/api/settings")
    async def put_settings(changes: dict):
        try:
            new = hub.settings.update(changes)
        except settings_mod.SettingsError as e:
            raise HTTPException(400, str(e))
        applied = False
        if hub.chat is not None and not hub.chat.busy:  # next question starts a fresh conversation with the new settings
            await hub.chat.close()
            hub.chat = None
            applied = True
        if "allow_peripheral_reads" in changes:  # re-check the expressions against the new policy
            for tgt, specs in list(hub.expr_specs.items()):
                hub.set_exprs(tgt, specs)
        return {"settings": new.to_dict(), "chat_restarted": applied}

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
        if not img.is_relative_to(ROOT.parent):
            raise HTTPException(400, "image must be inside the workspace repositories folder")
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
            return flash_mod.plan(req.target, cfg, img, ROOT, read,
                                  lambda s: s in list_serials() or probe is not None), cfg
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
            out[name] = sorted(str(Path(f).resolve()) for f in files)
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

    dist = ROOT / "ui" / "dist"
    if dist.is_dir():  # built UI (npm run build in ui/); API and /ws routes above take precedence
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def serve(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("rdt serve binds to loopback only")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
