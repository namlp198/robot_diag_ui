"""Phase 0 loss-against-rate sweep (port of robot_rc_rtos/tools/link_sweep/link_sweep.ps1), read-only.

The remote runs a build that steps its CONTROL gap (APP_TEST_LINK_SWEEP). rdt only observes:
  * step boundaries come from the remote's VCP lines "[sweep] step N gap G ms sent S" / "[sweep] done sent S"
    (S = frames the remote says it sent), or, when there is no VCP log, from changes of s_tx.out.sweep_step;
  * robot counters (accepted, lost, control_frames, crc_errors) are taken at the last sample at or before each
    boundary, on the PC clock. The two boards share no clock, so a boundary is only as exact as one poll period.
Loss of a step = lost / (accepted + lost), using robot counters only. A `lost` jump >= 200 in one sample is a remote
restart (SEQ wrap), not loss, and is removed from the step it falls in.
No flashing and no write: starting the sweep (resetting the remote) is the user's action.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass

from .analyzers import RESTART_LOST_JUMP, ROBOT, REMOTE, Data, steps

LINE = re.compile(r"\[sweep\]\s+(?:step\s+(\d+)\s+gap\s+(\d+)\s+ms|done)\s+sent\s+(\d+)")
PATHS = {
    "accepted": "s_lora_rx.filter.stats.accepted", "lost": "s_lora_rx.filter.stats.lost",
    "control": "s_lora_rx.control_frames", "crc": "s_lora_rx.parser.stats.crc_errors",
}
REMOTE_PATHS = {"step": "s_tx.out.sweep_step", "gap": "s_tx.out.sweep_gap_ms", "sent": "s_tx.out.control_frames"}


@dataclass
class Boundary:
    t: float
    gap_ms: int  # gap of the step that STARTS here (0 for "done")
    sent: int | None  # remote's own count at this boundary, if known
    source: str  # "vcp" | "variable"


@dataclass
class Row:
    gap_ms: int
    t0: float
    t1: float
    seconds: float
    sent: int | None
    control_rx: int
    accepted: int
    lost: int
    loss_pct: float
    crc_errors: int
    restarts_removed: int


def boundaries_from_log(lines: list[tuple[float, str]]) -> list[Boundary]:
    out = []
    for t, line in lines:
        m = LINE.search(line)
        if m:
            out.append(Boundary(t, int(m.group(2)) if m.group(2) else 0, int(m.group(3)), "vcp"))
    return out


def boundaries_from_variables(d: Data) -> list[Boundary]:
    got = d.col(REMOTE, REMOTE_PATHS["step"]), d.col(REMOTE, REMOTE_PATHS["gap"])
    if None in got:
        return []
    (t, step), (_t2, gap) = got
    sent = d.col(REMOTE, REMOTE_PATHS["sent"])
    def sent_at(i):
        return int(sent[1][i]) if sent else None

    edges = [i for i in range(1, len(t)) if step[i] != step[i - 1]]
    if not edges:
        return []  # sweep_step never changed: no sweep ran while recording
    # the first and last steps are bounded by the first and last sample
    out = [Boundary(t[0], int(gap[0]), sent_at(0), "variable")]
    out += [Boundary(t[i], int(gap[i]), sent_at(i), "variable") for i in edges]
    out.append(Boundary(t[-1], 0, sent_at(len(t) - 1), "variable"))
    return out


def _at(t: list[float], v: list, x: float):
    """Value at the last sample at or before x (first sample if x is earlier)."""
    lo = 0
    for i, ti in enumerate(t):
        if ti <= x:
            lo = i
        else:
            break
    return v[lo]


def compute(d: Data) -> dict:
    cols = {k: d.col(ROBOT, p) for k, p in PATHS.items()}
    missing = [PATHS[k] for k, c in cols.items() if c is None]
    if missing:
        return {"error": "robot variables not recorded: " + ", ".join(missing), "rows": []}
    b = boundaries_from_log(d.logs.get(REMOTE, []))
    source = "vcp"
    if len(b) < 2:
        b, source = boundaries_from_variables(d), "variable"
    if len(b) < 2:
        return {"error": "no sweep found: need '[sweep] ...' lines in the remote log, or s_tx.out.sweep_step changing. "
                         "The remote must run the sweep build and be reset after rdt starts reading.", "rows": []}
    tl, lost = cols["lost"]
    jumps = [(y, dv) for _x, y, dv in steps(tl, lost) if dv >= RESTART_LOST_JUMP]
    rows: list[Row] = []
    for a, z in zip(b, b[1:]):
        g = {k: (_at(*cols[k], z.t) - _at(*cols[k], a.t)) for k in cols}
        restarts = [dv for y, dv in jumps if a.t < y <= z.t]
        lost_n = int(g["lost"] - sum(restarts))
        acc = int(g["accepted"])
        rows.append(Row(a.gap_ms, round(a.t, 2), round(z.t, 2), round(z.t - a.t, 1),
                        (z.sent - a.sent) if a.sent is not None and z.sent is not None else None,
                        int(g["control"]), acc, lost_n,
                        round(100.0 * lost_n / (acc + lost_n), 1) if acc + lost_n else 0.0, int(g["crc"]), len(restarts)))
    return {"source": source, "rows": [asdict(r) for r in rows],
            "note": "boundaries are PC-clock estimates (poll period); sent is the remote's own count when available"}


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
