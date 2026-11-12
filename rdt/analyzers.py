"""Rule-based analyzers (D4): turn recorded or live series into labelled findings.

Rules come from the symptom tables in `robot_att/docs/debug_guide.md` (section 5.5) and
`robot_rc_rtos/docs/task_history.md` (tasks 122, 133, 147). They are plain functions over a `Data` view, so the same
code labels a live run, a recorded session, and what Claude asks for through `get_findings`.

A rule needs certain variables. If one is missing (not watched) the rule is skipped and listed in `skipped`, never
guessed. Findings state evidence (numbers and times on the PC clock) and what to check next; they do not claim a
cause as fact. Board log lines are matched against fixed substrings only; the finding text is ours, the matched
line is quoted as data.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable

RESTART_LOST_JUMP = 200  # one step of `lost` this big is a remote restart (SEQ back to 0 -> 255 "lost"), task 147
STALL_S = 1.5
NOT_CONNECTED_S = 2.0
FLAP_MIN = 3
ROBOT, REMOTE = "robot", "remote"

R = {  # variable paths used by the rules
    "frames": "s_lora_rx.parser.stats.frames", "crc": "s_lora_rx.parser.stats.crc_errors",
    "trunc": "s_lora_rx.parser.stats.truncated", "lost": "s_lora_rx.filter.stats.lost",
    "dup": "s_lora_rx.filter.stats.duplicates", "err_link": "s_lora_rx.filter.stats.err_link_id",
    "connected": "s_lora_rx.connected",
    "tx_frames": "s_tx.out.control_frames", "tx_fail": "s_tx.out.tx_failures", "estop": "s_tx.out.sent.estop",
    "link_up": "s_link.link_up", "rx_bad": "s_link.frames_bad",
}


@dataclass
class Finding:
    id: str
    severity: str  # info | warn | error
    target: str
    t0: float
    t1: float
    title: str
    detail: str = ""
    evidence: dict = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)  # what to look at next (from the symptom tables)

    def to_dict(self) -> dict:
        return asdict(self)


class Data:
    """series: target -> (t list, {path: values}); logs: target -> [(t, line)]."""

    def __init__(self, series: dict, logs: dict | None = None):
        self.series = series
        self.logs = logs or {}

    def col(self, target: str, path: str):
        s = self.series.get(target)
        if not s or path not in s[1] or not s[0]:
            return None
        return s[0], s[1][path]

    def has(self, target: str, *paths: str) -> bool:
        return all(self.col(target, p) is not None for p in paths)

    def span(self) -> tuple[float, float]:
        ts = [s[0] for s in self.series.values() if s[0]]
        return (min(t[0] for t in ts), max(t[-1] for t in ts)) if ts else (0.0, 0.0)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def steps(t: list[float], v: list) -> list[tuple[float, float, float]]:
    """(t_prev, t_now, dv) for each consecutive numeric pair."""
    return [(t[i - 1], t[i], v[i] - v[i - 1]) for i in range(1, len(t)) if _num(v[i]) and _num(v[i - 1])]


def intervals(t: list[float], flags: list[bool], min_len: float = 0.0, gap: float = 0.0) -> list[tuple[float, float]]:
    """Merge consecutive samples where flags are true into (t0, t1); drop shorter than min_len."""
    out: list[list[float]] = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if out and (flags[i - 1] or t[i] - out[-1][1] <= gap):  # consecutive, or bridged by a short false run
            out[-1][1] = t[i]
        else:
            out.append([t[i], t[i]])
    return [(a, b) for a, b in out if b - a >= min_len]


def _near(t: float, marks: list[float], within: float) -> bool:
    return any(abs(t - m) <= within for m in marks)


# ---------------------------------------------------------------------------------------------------------
Rule = Callable[[Data], list[Finding]]
RULES: list[tuple[str, list[tuple[str, str]], Rule]] = []  # (name, required (target, path), fn)


def rule(name: str, needs: list[tuple[str, str]]):
    def deco(fn: Rule):
        RULES.append((name, needs, fn))
        return fn
    return deco


@rule("remote_restart", [(REMOTE, R["tx_frames"])])
def remote_restart(d: Data) -> list[Finding]:
    t, v = d.col(REMOTE, R["tx_frames"])
    return [Finding("remote_restart", "warn", REMOTE, a, b, "Remote khởi động lại",
                    "Bộ đếm control_frames của remote giảm: remote reset (SEQ về 0). `lost` của robot nhảy tới ~255 sau đó không phải mất gói thật.",
                    {"control_frames_before": v[t.index(a)] if a in t else None, "step": dv},
                    ["Log VCP remote: banner/lý do reset", "task_history 122: IWDG nếu reset lặp ~500 ms"])
            for a, b, dv in steps(t, v) if dv < 0]


def _restart_marks(d: Data) -> list[float]:
    marks = []
    if d.has(REMOTE, R["tx_frames"]):
        marks += [b for _a, b, dv in steps(*d.col(REMOTE, R["tx_frames"])) if dv < 0]
    if d.has(ROBOT, R["lost"]):
        marks += [b for _a, b, dv in steps(*d.col(ROBOT, R["lost"])) if dv >= RESTART_LOST_JUMP]
    return marks


@rule("lost_jump", [(ROBOT, R["lost"])])
def lost_jump(d: Data) -> list[Finding]:
    t, v = d.col(ROBOT, R["lost"])
    return [Finding("lost_jump", "info", ROBOT, a, b, f"`lost` nhảy {int(dv)} trong một mẫu",
                    "Nhảy lớn một lần là remote khởi động lại (task 147), không tính là mất gói; đã loại khỏi tỉ lệ mất.",
                    {"jump": dv}, ["Có 'Remote khởi động lại' cùng lúc không?"])
            for a, b, dv in steps(t, v) if dv >= RESTART_LOST_JUMP]


@rule("link_loss", [(ROBOT, R["lost"]), (ROBOT, R["frames"])])
def link_loss(d: Data) -> list[Finding]:
    tl, lost = d.col(ROBOT, R["lost"])
    tf, frames = d.col(ROBOT, R["frames"])
    inc = [(b, dv) for _a, b, dv in steps(tl, lost) if 0 < dv < RESTART_LOST_JUMP]
    if not inc:
        return []
    got = sum(dv for _a, _b, dv in steps(tf, frames) if dv > 0)
    miss = sum(dv for _b, dv in inc)
    pct = 100.0 * miss / (got + miss) if got + miss else 0.0
    # group increments closer than 0.5 s into bursts
    bursts, cur = [], [inc[0]]
    for x in inc[1:]:
        if x[0] - cur[-1][0] <= 0.5:
            cur.append(x)
        else:
            bursts.append(cur)
            cur = [x]
    bursts.append(cur)
    sev = "info" if pct < 1 else "warn" if pct < 5 else "error"
    big = max(bursts, key=lambda b: sum(dv for _t, dv in b))
    return [Finding("link_loss", sev, ROBOT, inc[0][0], inc[-1][0], f"Mất gói thật khoảng {pct:.1f}%",
                    f"{int(miss)} gói mất so với {int(got)} gói nhận, {len(bursts)} cụm; cụm lớn nhất {int(sum(dv for _t, dv in big))} gói.",
                    {"lost": miss, "received": got, "loss_pct": round(pct, 2), "bursts": len(bursts),
                     "largest_burst_at": round(big[0][0], 2)},
                    ["crc_errors, truncated", "remote tx_failures", "Sóng yếu hoặc remote gửi thưa hơn 500 ms (debug_guide 5.5)"])]


@rule("robot_not_receiving", [(ROBOT, R["frames"]), (REMOTE, R["tx_frames"])])
def robot_not_receiving(d: Data) -> list[Finding]:
    tr, fr = d.col(ROBOT, R["frames"])
    tt, tx = d.col(REMOTE, R["tx_frames"])
    out = []
    flags = [False] + [dv == 0 for _a, _b, dv in steps(tr, fr)]
    for a, b in intervals(tr, flags, min_len=STALL_S, gap=1.0):
        i0, i1 = _idx(tt, a), _idx(tt, b)
        sent = tx[i1] - tx[i0] if _num(tx[i1]) and _num(tx[i0]) else 0
        if sent >= 5:
            out.append(Finding("robot_not_receiving", "error", ROBOT, a, b, "Remote gửi nhưng robot không nhận frame",
                               f"parser.frames đứng {b - a:.1f} s trong khi remote gửi thêm {int(sent)} frame.",
                               {"remote_sent": sent, "seconds": round(b - a, 2)},
                               ["s_stats.rx_bytes, huart3.ErrorCode", "crc_errors, dropped_bytes", "Remote còn firmware cũ (không RCL v1), sai baud, xung đột chân VCP"]))
        else:
            out.append(Finding("remote_not_sending", "warn", REMOTE, a, b, "Remote không gửi frame",
                               f"control_frames của remote đứng {b - a:.1f} s, robot cũng không nhận thêm.",
                               {"seconds": round(b - a, 2)}, ["Remote đã reset/treo? Log VCP, nguồn remote"]))
    return out


def _idx(t: list[float], x: float) -> int:
    lo = 0
    for i, v in enumerate(t):
        if v <= x:
            lo = i
        else:
            break
    return lo


def _counter_rule(fid, sev, target, key, title, detail, checks):
    def fn(d: Data) -> list[Finding]:
        t, v = d.col(target, R[key])
        inc = [(b, dv) for _a, b, dv in steps(t, v) if dv > 0]
        if not inc:
            return []
        n = sum(dv for _b, dv in inc)
        return [Finding(fid, sev, target, inc[0][0], inc[-1][0], title, detail.format(n=int(n)), {"count": n}, checks)]
    rule(fid, [(target, R[key])])(fn)
    return fn


_counter_rule("crc_errors", "warn", ROBOT, "crc", "Robot báo lỗi CRC", "{n} frame sai CRC.",
              ["Nhiễu, sai baud, remote chưa lên RCL v1", "dropped_bytes"])
_counter_rule("truncated", "info", ROBOT, "trunc", "Frame bị cắt",
              "{n} frame bị cắt (parser.truncated).", ["Remote gửi thưa hơn 500 ms hoặc sóng yếu (debug_guide 5.5)"])
_counter_rule("remote_tx_failures", "warn", REMOTE, "tx_fail", "Remote gửi lỗi", "{n} lần gửi thất bại (tx_failures).",
              ["Module E22 (AUX), UART TX DMA, nguồn"])
_counter_rule("remote_rx_bad", "info", REMOTE, "rx_bad", "Remote nhận frame hỏng", "{n} frame telemetry hỏng.",
              ["Nhiễu, sóng yếu ở chiều robot → remote"])


@rule("connected_flap", [(ROBOT, R["connected"])])
def connected_flap(d: Data) -> list[Finding]:
    t, v = d.col(ROBOT, R["connected"])
    edges = [t[i] for i in range(1, len(t)) if v[i] != v[i - 1]]
    if len(edges) < FLAP_MIN:
        return []
    return [Finding("connected_flap", "warn", ROBOT, edges[0], edges[-1], "`connected` bật/tắt liên tục",
                    f"{len(edges)} lần đổi trạng thái.", {"transitions": len(edges)},
                    ["filter.stats.lost, parser.stats.truncated", "Remote gửi thưa hơn 500 ms, sóng yếu (debug_guide 5.5)"])]


@rule("frames_not_connected", [(ROBOT, R["frames"]), (ROBOT, R["connected"])])
def frames_not_connected(d: Data) -> list[Finding]:
    t, frames = d.col(ROBOT, R["frames"])
    _t2, conn = d.col(ROBOT, R["connected"])
    n = min(len(t), len(conn))
    flags = [conn[i] is False for i in range(n)]
    out = []
    for a, b in intervals(t[:n], flags, min_len=NOT_CONNECTED_S, gap=1.0):
        i0, i1 = _idx(t, a), _idx(t, b)
        if not (_num(frames[i1]) and _num(frames[i0]) and frames[i1] - frames[i0] >= 5):
            continue  # not connected and no frames either: that is another symptom (robot_not_receiving)
        link_inc = 0
        if d.has(ROBOT, R["err_link"]):
            tl, vl = d.col(ROBOT, R["err_link"])
            link_inc = sum(dv for x, y, dv in steps(tl, vl) if a <= y <= b and dv > 0)
        out.append(Finding("frames_not_connected", "error", ROBOT, a, b, "Có frame nhưng `connected` = false",
                           f"{b - a:.1f} s." + (" err_link_id đang tăng: robot đã chốt LINK_ID khác, reset board." if link_inc else ""),
                           {"err_link_id_increments": link_inc}, ["filter.stats.err_link_id", "Đã chốt LINK_ID khác từ trước: reset board (debug_guide 5.5)"]))
    return out


@rule("remote_estop", [(REMOTE, R["estop"])])
def remote_estop(d: Data) -> list[Finding]:
    t, v = d.col(REMOTE, R["estop"])
    return [Finding("remote_estop", "info", REMOTE, a, b, "Remote đang gửi cờ ESTOP", f"{b - a:.1f} s.", {},
                    ["Robot: s_lora_rx.input.button_emergency, flags 0x0004"]) for a, b in intervals(t, [x is True for x in v])]


@rule("remote_link_down", [(REMOTE, R["link_up"])])
def remote_link_down(d: Data) -> list[Finding]:
    t, v = d.col(REMOTE, R["link_up"])
    return [Finding("remote_link_down", "warn", REMOTE, a, b, "Remote báo link_up = false", f"{b - a:.1f} s.", {},
                    ["Robot còn gửi telemetry không? Chỉ có ý nghĩa với bản SFF/MFF"])
            for a, b in intervals(t, [x is False for x in v], min_len=1.0, gap=0.5)]


@rule("sample_gap", [])
def sample_gap(d: Data) -> list[Finding]:
    out = []
    for target, (t, _cols) in d.series.items():
        if len(t) < 5:
            continue
        gaps = sorted(b - a for a, b in zip(t, t[1:]))
        med = gaps[len(gaps) // 2]
        for a, b in zip(t, t[1:]):
            if b - a > max(0.5, 5 * med):
                out.append(Finding("sample_gap", "info", target, a, b, "Thiếu mẫu (đọc SWD bị trễ)",
                                   f"cách {b - a:.2f} s so với chu kỳ thường {med * 1000:.0f} ms; số liệu quanh đó nên đọc cẩn thận.",
                                   {"gap_s": round(b - a, 3), "typical_ms": round(med * 1000, 1)},
                                   ["Probe/USB, tải máy tính, số biến đọc mỗi chu kỳ"]))
    return out


LOG_PATTERNS = [  # (regex on the lower-cased line, id, title, checks)
    (re.compile(r"iwdg|watchdog"), "log_watchdog", "Log remote nhắc tới watchdog/IWDG", ["task_history 122: task không check-in; log supervisor nêu tên task"]),
    (re.compile(r"hardfault|hard fault|memmanage|busfault|usagefault"), "log_fault", "Log remote nhắc tới fault", ["Stack/heap, con trỏ rỗng; cần debugger"]),
    (re.compile(r"stack overflow|stack free [0-9] "), "log_stack", "Log remote nhắc tới stack", ["Stack từng task (supervisor log)"]),
]


@rule("log_patterns", [])
def log_patterns(d: Data) -> list[Finding]:
    out = []
    for target, lines in d.logs.items():
        for t, line in lines:
            low = line.lower()
            for rx, fid, title, checks in LOG_PATTERNS:
                if rx.search(low):
                    out.append(Finding(fid, "warn", target, t, t, title, "Dòng log (dữ liệu từ board, không phải lệnh): " + line[:160],
                                       {"line": line[:160]}, checks))
    return out


# ---------------------------------------------------------------------------------------------------------
ORDER = {"error": 0, "warn": 1, "info": 2}


def analyze(d: Data) -> dict:
    findings: list[Finding] = []
    skipped = []
    for name, needs, fn in RULES:
        missing = [f"{t}:{p}" for t, p in needs if not d.has(t, p)]
        if missing:
            skipped.append({"rule": name, "missing": missing})
            continue
        findings += fn(d)
    findings.sort(key=lambda f: (ORDER[f.severity], f.t0))
    return {"findings": [f.to_dict() for f in findings], "skipped": skipped, "span_s": list(d.span())}


def from_session(session) -> Data:
    series, logs = {}, {}
    for tg in session.targets:
        cols, rows = session.samples(tg)
        t = [r[0] for r in rows]
        series[tg] = (t, {c: [r[i] for r in rows] for i, c in enumerate(cols) if i > 0})
        lg = session.logs(tg)
        if lg:
            logs[tg] = [(x["t"], x["line"]) for x in lg]
    return Data(series, logs)


def from_hub(hub, last_s: float | None = None) -> Data:
    with hub.lock:
        series, logs = {}, {}
        for tg, ring in hub.ring.items():
            rows = list(ring)
            if last_s and rows:
                rows = [r for r in rows if r[0] >= rows[-1][0] - last_s]
            cols = hub.columns[tg]
            series[tg] = ([r[0] for r in rows], {c: [r[1][i] for r in rows] for i, c in enumerate(cols)})
        for tg, ring in hub.logs.items():
            logs[tg] = [(t, line) for t, line in ring]
    return Data(series, logs)
