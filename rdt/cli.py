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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rdt")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve a variable path to address/size from the target ELF")
    r.add_argument("target")
    r.add_argument("path")
    r.set_defaults(fn=cmd_resolve)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
