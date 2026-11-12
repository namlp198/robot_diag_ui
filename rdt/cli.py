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
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
