"""Regenerate docs/REFERENCE.en.md and docs/REFERENCE.vi.md from rdt/reference.py. Usage: python -I scripts/gen_reference.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rdt.reference import to_markdown  # noqa: E402

for lang in ("en", "vi"):
    (ROOT / "docs" / f"REFERENCE.{lang}.md").write_text(to_markdown(lang), encoding="utf-8", newline="\n")
    print("wrote", f"docs/REFERENCE.{lang}.md")
