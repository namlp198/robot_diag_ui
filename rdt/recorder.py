"""Session recorder and reader.

A session is one directory under `sessions/` (git-ignored):

    meta.json              started/ended (UTC), per target: serial, ELF path + sha256 + git hash, variables
    samples_<target>.csv   t_s,<path>,<path>...   (t_s: seconds on the PC clock since session start)
    log_<target>.jsonl     one JSON object per line: {"t": seconds, "line": "<text>"}  (VCP log, escaped)
    events.jsonl           {"t": seconds, "kind": "...", "text": "..."}  (errors, annotations)

The boards share no clock, so every timestamp is taken on the PC when the sample arrives.
Text from boards is stored as JSON strings, never interpreted.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def git_hash(path: Path) -> str | None:
    d = path if path.is_dir() else path.parent
    try:
        out = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Recorder:
    """Thread-safe writer. `targets` maps name -> {"serial","elf","paths":[...], "vars":[Resolved...]}."""

    def __init__(self, root: Path, targets: dict, label: str = ""):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = Path(root) / (stamp + (f"_{label}" if label else ""))
        self.dir.mkdir(parents=True, exist_ok=False)
        self._lock = threading.Lock()
        self._files: dict[str, object] = {}
        self._csv: dict[str, csv.writer] = {}
        self.counts: dict[str, int] = {}
        self.meta = {"started_utc": _utc(), "ended_utc": None, "targets": {}}
        for name, t in targets.items():
            elf = Path(t["elf"])
            self.meta["targets"][name] = {
                "serial": t["serial"], "elf": str(elf), "elf_sha256": sha256_file(elf),
                "elf_repo_git": git_hash(elf), "paths": t["paths"],
                "variables": [{"path": v.path, "address": v.address, "size": v.size, "kind": v.kind,
                               "type": v.type_name} for v in t.get("vars", [])],
            }
            f = open(self.dir / f"samples_{name}.csv", "w", newline="", encoding="utf-8")
            self._files[f"samples_{name}"] = f
            w = csv.writer(f)
            w.writerow(["t_s"] + t["paths"])
            self._csv[name] = w
            self.counts[name] = 0
        self._events = open(self.dir / "events.jsonl", "w", encoding="utf-8")
        self._write_meta()

    def _write_meta(self):
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def add_sample(self, target: str, t: float, values: list):
        with self._lock:
            self._csv[target].writerow([f"{t:.6f}"] + list(values))
            self.counts[target] += 1

    def add_log(self, target: str, t: float, line: str):
        with self._lock:
            key = f"log_{target}"
            if key not in self._files:
                self._files[key] = open(self.dir / f"log_{target}.jsonl", "w", encoding="utf-8")
            self._files[key].write(json.dumps({"t": round(t, 6), "line": line}, ensure_ascii=True) + "\n")

    def add_can(self, target: str, t: float, frame: dict):
        """One sampled CAN frame (rdt.cantap): can_<target>.jsonl, {"t": ..., plus the frame fields}."""
        with self._lock:
            key = f"can_{target}"
            if key not in self._files:
                self._files[key] = open(self.dir / f"can_{target}.jsonl", "w", encoding="utf-8")
            self._files[key].write(json.dumps({"t": round(t, 6), **frame}, ensure_ascii=True) + "\n")

    def add_event(self, t: float, kind: str, text: str):
        with self._lock:
            self._events.write(json.dumps({"t": round(t, 6), "kind": kind, "text": text},
                                          ensure_ascii=True) + "\n")

    def close(self):
        with self._lock:
            for f in [*self._files.values(), self._events]:
                f.close()
            self._files.clear()
            self.meta["ended_utc"] = _utc()
            self.meta["sample_counts"] = dict(self.counts)
            self._write_meta()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _num(s: str):
    for conv in (int, float):
        try:
            return conv(s)
        except ValueError:
            pass
    if s in ("True", "False"):
        return s == "True"
    return s  # hex string for bytes variables


@dataclass
class Session:
    path: Path
    meta: dict

    @property
    def targets(self) -> list[str]:
        return list(self.meta["targets"])

    def samples(self, target: str) -> tuple[list[str], list[list]]:
        """Return (column names, rows). Row 0 of each row is t_s."""
        with open(self.path / f"samples_{target}.csv", newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            header = next(r)
            return header, [[float(row[0])] + [_num(c) for c in row[1:]] for row in r if row]

    def logs(self, target: str) -> list[dict]:
        p = self.path / f"log_{target}.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]

    def can(self, target: str) -> list[dict]:
        p = self.path / f"can_{target}.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x] if p.exists() else []

    def events(self) -> list[dict]:
        p = self.path / "events.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x] if p.exists() else []


def open_session(path: Path) -> Session:
    path = Path(path)
    return Session(path, json.loads((path / "meta.json").read_text(encoding="utf-8")))


def list_sessions(root: Path) -> list[Path]:
    root = Path(root)
    return sorted(p for p in root.glob("*") if (p / "meta.json").exists()) if root.exists() else []
