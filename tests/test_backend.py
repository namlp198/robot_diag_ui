import os
from pathlib import Path

import pytest

pyocd = pytest.importorskip("pyocd")

from rdt.backend import BackendError, Probe, list_serials  # noqa: E402
from rdt.cli import load_targets  # noqa: E402
from rdt.symbols import SymbolTable  # noqa: E402

ROOT = Path(__file__).parents[1]


def _target(name):
    # Probe access can block inside libusb enumeration (seen while CubeIDE was open), so hardware tests are opt-in.
    if not os.environ.get("RDT_HW_TESTS"):
        pytest.skip("hardware test: set RDT_HW_TESTS=1 to run")
    t = load_targets()[name]
    elf = (ROOT / t["elf"]).resolve()
    if not elf.exists():
        pytest.skip("ELF not built")
    if t["probe_serial"] not in list_serials():
        pytest.skip(f"probe for {name} not attached")
    return t, elf


def test_robot_read_matches_size():
    t, elf = _target("robot")
    st = SymbolTable(elf)
    r = st.resolve("s_lora_rx")
    st.close()
    try:
        p = Probe(t["probe_serial"]).open()
    except BackendError as e:  # probe listed but the target is unpowered: skip, do not fail
        pytest.skip(f"target not attachable: {e}")
    with p:
        assert len(p.read(r.address, r.size)) == r.size
