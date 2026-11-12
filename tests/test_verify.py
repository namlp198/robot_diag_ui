from pathlib import Path

import pytest

from rdt.verify import chunk_plan, flash_image, verify

ELF = Path(__file__).parents[2] / "robot_att/CM7/Debug/robot_att_H7_CM7.elf"


def test_chunk_plan_synthetic():
    img = [(0x08000000, bytes(range(256)) * 4), (0x08001000, b"\xaa" * 512)]
    plan = chunk_plan(img, chunks=8, size=64)
    assert len(plan) == 8 and plan[0][0] == 0x08000000
    assert all(len(d) == 64 for _, d in plan)


@pytest.mark.skipif(not ELF.exists(), reason="robot_att ELF not built")
def test_verify_matches_image_and_detects_difference():
    mem = {}
    for a, d in flash_image(ELF):
        mem[a] = d

    def read(addr, n):
        for a, d in mem.items():
            if a <= addr and addr + n <= a + len(d):
                return d[addr - a:addr - a + n]
        raise IOError("unmapped")

    assert verify(read, ELF).ok
    r = verify(lambda a, n: b"\x00" * n, ELF)
    assert not r.ok and r.mismatched and "MISMATCH" in r.summary()
    r = verify(lambda a, n: (_ for _ in ()).throw(IOError("no probe")), ELF)
    assert not r.ok and r.error and "not verified" in r.summary()
