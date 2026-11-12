import re
from pathlib import Path

from rdt.reference import MONITORED, REFERENCE, SAFETY, to_markdown

ROOT = Path(__file__).parents[1]


def test_every_dashboard_variable_is_documented():
    src = (ROOT / "ui" / "src" / "panels.js").read_text(encoding="utf-8")
    paths = set(re.findall(r"'(s_[A-Za-z0-9_.]+)'", src))
    assert paths, "no variables found in panels.js"
    missing = paths - {m["name"] for m in MONITORED}
    assert not missing, f"add to rdt/reference.py MONITORED: {sorted(missing)}"


def test_entries_are_bilingual_and_well_formed():
    for key in ("pyocd_api", "pyocd_cli", "cube_cli"):
        for c in REFERENCE[key]:
            assert c["en"] and c["vi"] and c["syntax"] and c["safety"] in SAFETY
    for m in MONITORED:
        assert m["en"] and m["vi"]


def test_generated_docs_are_current():
    for lang in ("en", "vi"):
        f = ROOT / "docs" / f"REFERENCE.{lang}.md"
        assert f.read_text(encoding="utf-8").replace("\r\n", "\n") == to_markdown(lang), "run: python -I scripts/gen_reference.py"


def test_rdt_only_marks_read_commands_as_used_except_flash():
    allowed_write = {"-w", "-rst"}  # the gated flash command
    for c in REFERENCE["cube_cli"]:
        if c["used_by_rdt"] and c["safety"] in ("write", "control", "danger"):
            assert c["name"] in allowed_write, c["name"]
