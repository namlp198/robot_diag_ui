"""rdt CLI. Hardware-free commands only for now; watch/record need the probe backend (spike S1)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .symbols import SymbolError, SymbolTable

ROOT = Path(__file__).resolve().parents[1]


def load_targets(path: Path | None = None) -> dict:
    path = path or ROOT / "targets.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["targets"]


def cmd_resolve(args) -> int:
    targets = load_targets()
    if args.target not in targets:
        print(f"unknown target {args.target!r}; have: {', '.join(targets)}", file=sys.stderr)
        return 2
    elf = (ROOT / targets[args.target]["elf"]).resolve()
    st = SymbolTable(elf)
    try:
        r = st.resolve(args.path)
    except SymbolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        st.close()
    print(f"{r.path}  addr=0x{r.address:08X} size={r.size} kind={r.kind} type={r.type_name}")
    return 0


def cmd_watch(args) -> int:
    import time

    from .backend import BackendError, Probe

    targets = load_targets()
    if args.target not in targets:
        print(f"unknown target {args.target!r}; have: {', '.join(targets)}", file=sys.stderr)
        return 2
    t = targets[args.target]
    st = SymbolTable((ROOT / t["elf"]).resolve())
    try:
        vars_ = [st.resolve(p) for p in args.paths]
    except SymbolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        st.close()
    period = 1.0 / args.hz
    try:
        with Probe(t["probe_serial"]) as probe:
            print("t_s," + ",".join(v.path for v in vars_))
            t0 = time.perf_counter()
            n = 0
            while args.count == 0 or n < args.count:
                tick = time.perf_counter()
                vals = [v.decode(probe.read(v.address, v.size)) for v in vars_]
                vals = [x.hex() if isinstance(x, (bytes, bytearray)) else x for x in vals]
                print(f"{tick - t0:.3f}," + ",".join(str(x) for x in vals), flush=True)
                n += 1
                time.sleep(max(0.0, period - (time.perf_counter() - tick)))
    except BackendError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def cmd_record(args) -> int:
    import time

    from .recorder import Recorder
    from .sampler import Sampler

    targets = load_targets()
    by_target: dict[str, list[str]] = {}
    for spec in args.specs:
        name, _, path = spec.partition(":")
        if name not in targets or not path:
            print(f"bad spec {spec!r}; use <target>:<variable path>; targets: {', '.join(targets)}",
                  file=sys.stderr)
            return 2
        by_target.setdefault(name, []).append(path)
    t0 = time.perf_counter()
    samplers: list[Sampler] = []
    try:
        for name, paths in by_target.items():
            t = targets[name]
            elf = (ROOT / t["elf"]).resolve()
            samplers.append(Sampler(name, t["probe_serial"], elf, paths, args.hz, lambda *a: None, t0))
    except SymbolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    info = {s.target: {"serial": s.serial, "elf": str((ROOT / targets[s.target]["elf"]).resolve()),
                       "paths": s.paths, "vars": s.vars} for s in samplers}
    root = ROOT / "sessions"
    root.mkdir(exist_ok=True)
    with Recorder(root, info, label=args.label) as rec:
        for s in samplers:
            s.sink = lambda target, t, vals: rec.add_sample(target, t, vals)
            s.on_error = lambda target, msg: rec.add_event(time.perf_counter() - t0, f"error:{target}", msg)
            s.start()
        print(f"recording to {rec.dir} (Ctrl+C to stop)", file=sys.stderr)
        try:
            end = t0 + args.seconds if args.seconds else None
            while end is None or time.perf_counter() < end:
                time.sleep(0.2)
                if not any(s.is_alive() for s in samplers):
                    break
        except KeyboardInterrupt:
            pass
        for s in samplers:
            s.stop()
        for s in samplers:
            s.join(timeout=3)
        for s in samplers:
            print(f"{s.target}: {s.reads} samples, {s.failures} read failures", file=sys.stderr)
    print(rec.dir)
    return 0


def cmd_replay(args) -> int:
    from .recorder import list_sessions, open_session

    if args.session is None:
        for p in list_sessions(ROOT / "sessions"):
            print(p.name)
        return 0
    path = Path(args.session)
    if not path.exists():
        path = ROOT / "sessions" / args.session
    s = open_session(path)
    print(f"session {path.name}: {s.meta['started_utc']} .. {s.meta['ended_utc']}")
    for name in s.targets:
        cols, rows = s.samples(name)
        m = s.meta["targets"][name]
        print(f"[{name}] serial {m['serial']} elf_sha256 {(m['elf_sha256'] or '?')[:12]} "
              f"git {(m['elf_repo_git'] or '?')[:8]} samples {len(rows)}")
        if rows:
            dur = rows[-1][0] - rows[0][0]
            print(f"  span {dur:.2f} s, {len(rows) / dur if dur else 0:.1f} Hz")
        if args.csv:
            print(",".join(cols))
            for r in rows:
                print(",".join(str(x) for x in r))
        else:
            for i, c in enumerate(cols[1:], start=1):
                vals = [r[i] for r in rows]
                nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
                if nums and len(nums) == len(vals):
                    print(f"  {c}: min {min(nums)} max {max(nums)} last {nums[-1]}")
                elif vals:
                    print(f"  {c}: {len(set(map(str, vals)))} distinct values, last {str(vals[-1])[:40]}")
    for e in s.events()[:20]:
        print(f"event t={e['t']}: {e['kind']}: {e['text']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rdt")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve a variable path to address/size from the target ELF")
    r.add_argument("target")
    r.add_argument("path")
    r.set_defaults(fn=cmd_resolve)
    w = sub.add_parser("watch", help="read variables over SWD (read-only) and print CSV")
    w.add_argument("target")
    w.add_argument("paths", nargs="+")
    w.add_argument("--hz", type=float, default=10.0)
    w.add_argument("--count", type=int, default=0, help="stop after N samples (0 = until Ctrl+C)")
    w.set_defaults(fn=cmd_watch)
    rc = sub.add_parser("record", help="record variables of one or more targets into sessions/<stamp>")
    rc.add_argument("specs", nargs="+", help="<target>:<variable path>, e.g. robot:s_lora_rx.filter.stats.lost")
    rc.add_argument("--hz", type=float, default=20.0)
    rc.add_argument("--seconds", type=float, default=0.0, help="0 = until Ctrl+C")
    rc.add_argument("--label", default="")
    rc.set_defaults(fn=cmd_record)
    rp = sub.add_parser("replay", help="list sessions, or summarise / dump one")
    rp.add_argument("session", nargs="?")
    rp.add_argument("--csv", action="store_true")
    rp.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
