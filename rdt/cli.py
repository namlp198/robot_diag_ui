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


def elf_paths(cfg: dict) -> tuple[Path, Path | None]:
    """(ELF with types, ELF really flashed or None). `image_elf` is for Release builds, which carry no DWARF."""
    elf = (ROOT / cfg["elf"]).resolve()
    image = (ROOT / cfg["image_elf"]).resolve() if cfg.get("image_elf") else None
    return elf, image


def open_symbols(cfg: dict) -> SymbolTable:
    elf, image = elf_paths(cfg)
    return SymbolTable(elf, addr_from=image)


def cmd_resolve(args) -> int:
    targets = load_targets()
    if args.target not in targets:
        print(f"unknown target {args.target!r}; have: {', '.join(targets)}", file=sys.stderr)
        return 2
    st = open_symbols(targets[args.target])
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
    st = open_symbols(t)
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
    from .vcp import VcpError, VcpReader

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
            elf, image = elf_paths(t)
            samplers.append(Sampler(name, t["probe_serial"], elf, paths, args.hz, lambda *a: None, t0,
                                    image=image))
    except SymbolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    info = {s.target: {"serial": s.serial, "elf": str(s.image),
                       "paths": s.paths, "vars": s.vars} for s in samplers}
    box: list = [None]  # the recorder, filled in below; readers are built first so bad input creates no session
    readers = []
    for name in args.vcp:
        if name not in targets:
            print(f"unknown --vcp target {name!r}", file=sys.stderr)
            return 2
        try:
            readers.append(VcpReader(
                name, targets[name], lambda target, t, line: box[0].add_log(target, t, line), t0,
                lambda target, msg: box[0].add_event(time.perf_counter() - t0, f"error:{target}", msg)))
        except VcpError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    root = ROOT / "sessions"
    root.mkdir(exist_ok=True)
    with Recorder(root, info, label=args.label) as rec:
        box[0] = rec
        for r in readers:
            r.start()
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
        for s in [*samplers, *readers]:
            s.stop()
        for s in [*samplers, *readers]:
            s.join(timeout=3)
        for r in readers:
            print(f"{r.target}: {r.lines} VCP lines on {r.port}", file=sys.stderr)
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


def cmd_analyze(args) -> int:
    import json

    from . import analyzers
    from .recorder import open_session

    path = Path(args.session)
    if not path.exists():
        path = ROOT / "sessions" / args.session
    res = analyzers.analyze(analyzers.from_session(open_session(path)))
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    print(f"session {path.name}: span {res['span_s'][0]:.1f}..{res['span_s'][1]:.1f} s, {len(res['findings'])} findings")
    for f in res["findings"]:
        print(f"[{f['severity']:5}] {f['target']:6} {f['t0']:7.2f}-{f['t1']:7.2f}  {f['title']}: {f['detail']}")
        for c in f["checks"]:
            print(f"          check: {c}")
    if res["skipped"]:
        print("skipped (variables not recorded):", ", ".join(f"{x['rule']}" for x in res["skipped"]))
    return 0


def cmd_sweep(args) -> int:
    from . import analyzers, sweep
    from .recorder import open_session

    path = Path(args.session)
    if not path.exists():
        path = ROOT / "sessions" / args.session
    res = sweep.compute(analyzers.from_session(open_session(path)))
    if res.get("error"):
        print("error:", res["error"], file=sys.stderr)
        return 1
    if args.csv:
        print(sweep.to_csv(res["rows"]), end="")
        return 0
    print(f"sweep in {path.name} (boundaries from {res['source']})")
    print(f"{'gap_ms':>7} {'sec':>6} {'sent':>6} {'rx':>6} {'accepted':>8} {'lost':>5} {'loss%':>6} {'crc':>4}")
    for r in res["rows"]:
        sent = r["sent"] if r["sent"] is not None else "-"
        print(f"{r['gap_ms']:>7} {r['seconds']:>6} {sent:>6} {r['control_rx']:>6} "
              f"{r['accepted']:>8} {r['lost']:>5} {r['loss_pct']:>6} {r['crc_errors']:>4}")
    print(res["note"])
    return 0


def cmd_flash_plan(args) -> int:
    """Dry run only. Programming is available through the daemon API/UI with an explicit confirmation."""
    import json

    from .backend import BackendError, Probe, list_serials
    from . import flash

    targets = load_targets()
    if args.target not in targets:
        print(f"unknown target {args.target!r}", file=sys.stderr)
        return 2
    cfg = targets[args.target]
    img = Path(args.image)
    img = (img if img.is_absolute() else ROOT / img).resolve()
    try:
        probe = Probe(cfg["probe_serial"]).open()
    except BackendError as e:
        print(f"note: probe not readable: {e}", file=sys.stderr)
        probe = None
    try:
        p = flash.plan(args.target, cfg, img, ROOT, probe.read if probe else None,
                       lambda s: s in list_serials() or probe is not None)
    except flash.FlashError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if probe:
            probe.close()
    if args.json:
        print(json.dumps(p.to_dict(), indent=2))
    else:
        for c in p.checks:
            print(f"[{'ok' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
        print("already flashed (no-op):", p.already_flashed)
        print("command:", " ".join(p.command))
        print("confirm phrase:", p.confirm, "| robot also needs motors_safe:", p.needs_motors_safe)
        print("PLAN OK" if p.ok else "PLAN REFUSED")
    return 0 if p.ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Vietnamese text must not crash a cp1252 console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
    rc.add_argument("--vcp", action="append", default=[], metavar="TARGET",
                    help="also record the VCP log of TARGET (refused when its log_port is null)")
    rc.set_defaults(fn=cmd_record)
    sv = sub.add_parser("serve", help="run the daemon (HTTP + WebSocket on 127.0.0.1)")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(fn=lambda a: __import__("rdt.daemon", fromlist=["serve"]).serve(port=a.port) or 0)
    ap_ = sub.add_parser("app", help="the UI in its own native window (needs: pip install -e .[app])")
    ap_.add_argument("--port", type=int, default=8765)
    ap_.set_defaults(fn=lambda a: __import__("rdt.app", fromlist=["run"]).run(port=a.port))
    an = sub.add_parser("analyze", help="label a recorded session with rule-based findings")
    an.add_argument("session")
    an.add_argument("--json", action="store_true")
    an.set_defaults(fn=cmd_analyze)
    sw = sub.add_parser("sweep", help="loss-against-rate table of a recorded Phase 0 sweep")
    sw.add_argument("session")
    sw.add_argument("--csv", action="store_true")
    sw.set_defaults(fn=cmd_sweep)
    fp = sub.add_parser("flash-plan", help="dry run of a flash: checks and command, writes nothing")
    fp.add_argument("target")
    fp.add_argument("image")
    fp.add_argument("--json", action="store_true")
    fp.set_defaults(fn=cmd_flash_plan)
    rp = sub.add_parser("replay", help="list sessions, or summarise / dump one")
    rp.add_argument("session", nargs="?")
    rp.add_argument("--csv", action="store_true")
    rp.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
