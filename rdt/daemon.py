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

from .cli import ROOT, load_targets
from .recorder import Recorder, list_sessions, open_session
from .sampler import Sampler
from .symbols import SymbolError, SymbolTable
from .vcp import VcpError, VcpReader

RING = 4000  # samples kept per target for late-joining clients
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
                    samplers.append(Sampler(name, t["probe_serial"], (ROOT / t["elf"]).resolve(), paths,
                                            req.hz, self.on_sample, t0, self.on_error))
                for name in req.vcp:
                    readers.append(VcpReader(name, self.targets[name], self.on_log, t0, self.on_error))
            except (SymbolError, VcpError, OSError) as e:
                raise HTTPException(400, str(e))
            self.t0 = t0
            self.samplers, self.readers = samplers, readers
            self.ring = {s.target: deque(maxlen=RING) for s in samplers}
            self.logs = {r.target: deque(maxlen=RING) for r in readers}
            self.columns = {s.target: s.paths for s in samplers}
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
            info = {s.target: {"serial": s.serial, "elf": str((ROOT / self.targets[s.target]["elf"]).resolve()),
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

    def status(self) -> dict:
        with self.lock:
            return {
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
        yield
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
        st = SymbolTable((ROOT / hub.targets[target]["elf"]).resolve())
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
        st = SymbolTable((ROOT / hub.targets[target]["elf"]).resolve())
        try:
            r = st.resolve(path)
        except SymbolError as e:
            raise HTTPException(400, str(e))
        finally:
            st.close()
        return {"path": r.path, "address": r.address, "size": r.size, "kind": r.kind, "type": r.type_name}

    @app.get("/api/members")
    def members(target: str, path: str, limit: int = 256):
        if target not in hub.targets:
            raise HTTPException(404, "unknown target")
        st = SymbolTable((ROOT / hub.targets[target]["elf"]).resolve())
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
