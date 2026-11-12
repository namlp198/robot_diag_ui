"""Tools Claude can call, as plain functions over the daemon Hub (no SDK import, so they are unit-testable).

Read tools return numbers and escaped text only. Text that came from a board (VCP lines, strings) is wrapped as
`{"untrusted_board_text": [...]}`: it is data to analyse, never instructions. There is no tool that writes target
memory, halts, resets or flashes; the bridge also denies every tool outside `mcp__rdt__*`.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .recorder import list_sessions, open_session
from .symbols import SymbolError

MAX_POINTS = 400
MAX_LOG = 200
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _stats(vals: list) -> dict:
    nums = [v for v in vals if _num(v)]
    if not nums or len(nums) != len(vals):
        distinct = sorted({str(v) for v in vals})
        return {"kind": "non-numeric", "distinct": len(distinct), "values": distinct[:8], "last": vals[-1] if vals else None}
    n = len(nums)
    mean = sum(nums) / n
    return {"kind": "numeric", "n": n, "min": min(nums), "max": max(nums), "mean": round(mean, 4),
            "first": nums[0], "last": nums[-1], "changes": sum(1 for a, b in zip(nums, nums[1:]) if a != b)}


def _downsample(t: list[float], v: list, max_points: int) -> tuple[list[float], list]:
    if len(t) <= max_points:
        return t, v
    step = len(t) / max_points
    idx = sorted({int(i * step) for i in range(max_points)} | {len(t) - 1})
    return [t[i] for i in idx], [v[i] for i in idx]


def _rate(t: list[float], v: list) -> float | None:
    if len(t) < 2 or not all(_num(x) for x in v) or t[-1] <= t[0]:
        return None
    return round((v[-1] - v[0]) / (t[-1] - t[0]), 4)


class ToolBox:
    """`hub` is rdt.daemon.Hub. `ui` publishes a display command to the UI: ui(dict)."""

    def __init__(self, hub, ui=lambda msg: None):
        self.hub = hub
        self.ui = ui
        self.view: dict = {}  # last view context sent by the UI (window, series)

    # --- data tools -------------------------------------------------------------------------
    def get_status(self) -> dict:
        s = self.hub.status()
        s["note"] = "t values are seconds on the PC clock since the run started; the two boards share no clock"
        return s

    def read_latest(self, target: str, paths: list[str] | None = None) -> dict:
        with self.hub.lock:
            ring = self.hub.ring.get(target)
            if not ring:
                return {"error": f"{target!r} has no samples; watched: {sorted(self.hub.ring)}"}
            t, vals = ring[-1]
            cols = self.hub.columns[target]
            want = paths or cols
            missing = [p for p in want if p not in cols]
            return {"target": target, "t": round(t, 3), "values": {p: vals[cols.index(p)] for p in want if p in cols},
                    "not_watched": missing}

    def get_series(self, target: str, path: str, last_s: float = 30.0, max_points: int = 200) -> dict:
        with self.hub.lock:
            ring = self.hub.ring.get(target)
            cols = self.hub.columns.get(target, [])
            if not ring or path not in cols:
                return {"error": f"{target}:{path} is not being watched; watched: {self.hub.columns}"}
            i = cols.index(path)
            end = ring[-1][0]
            rows = [(t, v[i]) for t, v in ring if t >= end - last_s]
        t = [r[0] for r in rows]
        v = [r[1] for r in rows]
        ts, vs = _downsample(t, v, min(max_points, MAX_POINTS))
        return {"target": target, "path": path, "window_s": [round(t[0], 3), round(t[-1], 3)], "stats": _stats(v),
                "rate_per_s": _rate(t, v), "points": [[round(a, 3), b] for a, b in zip(ts, vs)]}

    def get_log(self, target: str, last_s: float = 60.0, contains: str = "", limit: int = 100) -> dict:
        with self.hub.lock:
            ring = self.hub.logs.get(target)
            if ring is None:
                return {"error": f"no VCP log for {target!r} (robot has none)"}
            end = self.hub.ring.get(target, [(0, 0)])[-1][0] if self.hub.ring.get(target) else (ring[-1][0] if ring else 0)
            rows = [(t, s) for t, s in ring if t >= end - last_s and contains.lower() in s.lower()]
        rows = rows[-min(limit, MAX_LOG):]
        return {"target": target, "untrusted_board_text": [{"t": round(t, 3), "line": _CTRL.sub("?", s)} for t, s in rows]}

    def find_symbols(self, target: str, query: str, limit: int = 30) -> dict:
        from .cli import open_symbols
        if target not in self.hub.targets:
            return {"error": f"unknown target {target!r}"}
        st = open_symbols(self.hub.targets[target])
        try:
            out = []
            for n in [n for n in st.names() if query.lower() in n.lower()][:limit]:
                r = st.resolve(n)
                out.append({"path": r.path, "size": r.size, "kind": r.kind, "type": r.type_name})
            return {"target": target, "matches": out}
        finally:
            st.close()

    def members(self, target: str, path: str) -> dict:
        from .cli import open_symbols
        if target not in self.hub.targets:
            return {"error": f"unknown target {target!r}"}
        st = open_symbols(self.hub.targets[target])
        try:
            return {"target": target, "path": path,
                    "members": [{"path": r.path, "size": r.size, "kind": r.kind, "type": r.type_name}
                                for r in st.members(path, 64)]}
        except SymbolError as e:
            return {"error": str(e)}
        finally:
            st.close()

    def list_sessions(self) -> dict:
        out = []
        for p in list_sessions(self.hub.sessions_dir)[-30:]:
            s = open_session(p)
            out.append({"name": p.name, "started_utc": s.meta["started_utc"], "targets": s.targets,
                        "samples": s.meta.get("sample_counts")})
        return {"sessions": out}

    def session_summary(self, name: str, target: str, t0: float | None = None, t1: float | None = None) -> dict:
        if "/" in name or "\\" in name or ".." in name or not (self.hub.sessions_dir / name / "meta.json").exists():
            return {"error": "no such session"}
        s = open_session(self.hub.sessions_dir / name)
        if target not in s.targets:
            return {"error": f"target not in session; have {s.targets}"}
        cols, rows = s.samples(target)
        rows = [r for r in rows if (t0 is None or r[0] >= t0) and (t1 is None or r[0] <= t1)]
        if not rows:
            return {"error": "no samples in that window"}
        t = [r[0] for r in rows]
        res = {"session": name, "target": target, "window_s": [t[0], t[-1]], "samples": len(rows), "variables": {}}
        for j, c in enumerate(cols[1:], start=1):
            v = [r[j] for r in rows]
            res["variables"][c] = {**_stats(v), "rate_per_s": _rate(t, v)}
        res["elf_sha256"] = s.meta["targets"][target].get("elf_sha256")
        return res

    def get_findings(self, session: str | None = None, last_s: float = 120.0) -> dict:
        """Rule-based findings for the live run (last_s) or a recorded session. Rules and evidence are ours."""
        from . import analyzers
        if session:
            if "/" in session or "\\" in session or ".." in session or not (self.hub.sessions_dir / session / "meta.json").exists():
                return {"error": "no such session"}
            return analyzers.analyze(analyzers.from_session(open_session(self.hub.sessions_dir / session)))
        if not self.hub.ring:
            return {"error": "not running; pass a session name or start reading"}
        return analyzers.analyze(analyzers.from_hub(self.hub, last_s))

    # --- display tools (drive the UI) -------------------------------------------------------------
    def show_chart(self, series: list[dict], from_s: float | None = None, to_s: float | None = None,
                   title: str = "") -> dict:
        """series: [{"target": "robot", "path": "s_lora_rx.filter.stats.lost", "as": "rate"|"value"}]"""
        clean = []
        for s in series[:6]:
            if s.get("target") not in self.hub.targets or not isinstance(s.get("path"), str):
                return {"error": f"bad series entry {s!r}"}
            clean.append({"target": s["target"], "path": s["path"], "as": "rate" if s.get("as") == "rate" else "value"})
        self.ui({"cmd": "show_chart", "series": clean, "from": from_s, "to": to_s, "title": title[:120]})
        return {"ok": True}

    def annotate(self, t: float, text: str, target: str = "") -> dict:
        self.ui({"cmd": "annotate", "t": t, "text": text[:300], "target": target})
        return {"ok": True}

    def highlight_range(self, t0: float, t1: float, label: str = "") -> dict:
        self.ui({"cmd": "highlight", "t0": t0, "t1": t1, "label": label[:120]})
        return {"ok": True}

    def get_view_context(self) -> dict:
        return self.view or {"note": "the user has not selected anything in the UI"}


def finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
