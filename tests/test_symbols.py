from pathlib import Path

import pytest

from rdt.symbols import SymbolError, SymbolTable

ELF = Path(__file__).parents[2] / "robot_att/CM7/Debug/robot_att_H7_CM7.elf"
pytestmark = pytest.mark.skipif(not ELF.exists(), reason="robot_att ELF not built")


@pytest.fixture(scope="module")
def st():
    t = SymbolTable(ELF)
    yield t
    t.close()


def test_root_matches_symtab(st):
    r = st.resolve("s_lora_rx")
    assert r.address == 0x240005AC and r.size == 164 and r.kind == "struct"


def test_nested_member_inside_root(st):
    root = st.resolve("s_lora_rx")
    r = st.resolve("s_lora_rx.filter.stats.lost")
    assert root.address < r.address < root.address + root.size
    assert r.kind in ("uint", "int") and r.size in (1, 2, 4)
    assert r.decode((5).to_bytes(r.size, "little")) == 5


def test_errors(st):
    for bad in ("nope", "s_lora_rx.nope", "s_lora_rx[0]", "s_lora_rx..x"):
        with pytest.raises(SymbolError):
            st.resolve(bad)
