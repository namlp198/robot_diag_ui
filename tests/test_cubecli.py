import subprocess

import pytest

from rdt import cubecli

CFG = {"probe_serial": "SN123", "flash_range": [0x08000000, 0x080FFFFF]}


def test_builds_only_read_only_commands_with_hotplug():
    for cmd in ("info", "ob_display"):
        a = cubecli.build(cmd, CFG)
        assert "mode=HOTPLUG" in a and "sn=SN123" in a
        assert not {"-w", "-e", "-rst", "-halt", "-run", "-hardRst"} & set(a)
    assert cubecli.build("list", None)[1:] == ["-l", "st-link"]
    assert cubecli.build("read32", CFG, "0x08000000", "16")[-3:] == ["-r32", "0x08000000", "16"]


@pytest.mark.parametrize("cmd", ["flash", "erase", "reset", "halt", "-w", ""])
def test_rejects_unknown_commands(cmd):
    with pytest.raises(cubecli.CubeCliError):
        cubecli.build(cmd, CFG)


@pytest.mark.parametrize("addr,size", [
    ("0x40000000", 4),        # peripheral: reads can clear flags
    ("0x08000002", 4),        # unaligned
    ("0x08000000", 6),        # size not multiple of 4
    ("0x08000000", 8192),     # too big
    ("0x080FFFFC", 8),        # runs past the end of flash
    ("zzz", 4),
    ("0x5C001000", 4),        # DBGMCU is a peripheral address too
])
def test_rejects_unsafe_reads(addr, size):
    with pytest.raises(cubecli.CubeCliError):
        cubecli.build("read32", CFG, addr, size)


def test_allows_flash_and_sram_reads():
    cubecli.build("read32", CFG, "0x20000000", 64)
    cubecli.build("read32", CFG, "0x24000100", 64)
    cubecli.build("read32", CFG, "0x080FFFFC", 4)


def test_run_strips_ansi_and_reports(tmp_path):
    exe = tmp_path / "x.exe"
    exe.write_text("")
    fake = lambda args, **k: subprocess.CompletedProcess(args, 0, "\x1b[32mok\x1b[0m\n", "")
    r = cubecli.run([str(exe), "-l"], runner=fake)
    assert r["output"] == "ok\n" and r["returncode"] == 0


def test_run_missing_tool_is_an_error(tmp_path):
    with pytest.raises(cubecli.CubeCliError):
        cubecli.run([str(tmp_path / "nope.exe")])
