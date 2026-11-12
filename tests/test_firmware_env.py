import json
import subprocess

import pytest

from rdt import envcheck, firmware


def rec(addr, data, typ=0):
    b = bytes([len(data), addr >> 8, addr & 0xFF, typ]) + bytes(data)
    return ":" + (b + bytes([(-sum(b)) & 0xFF])).hex().upper()


def test_intel_hex_blocks_bases_and_errors():
    text = "\n".join([rec(0, [0x08, 0x00], 4), rec(0x0000, [1, 2, 3, 4]), rec(0x0004, [5, 6]), rec(0x0100, [9]), ":00000001FF"])
    assert firmware.parse_ihex(text) == [(0x08000000, bytes([1, 2, 3, 4, 5, 6])), (0x08000100, b"\x09")]
    with pytest.raises(firmware.FirmwareError, match="checksum"):
        firmware.parse_ihex(":0400000001020304FF\n:00000001FF")
    with pytest.raises(firmware.FirmwareError, match="end-of-file"):
        firmware.parse_ihex(rec(0, [1]))
    with pytest.raises(firmware.FirmwareError, match="not an Intel HEX"):
        firmware.parse_ihex("hello")
    with pytest.raises(firmware.FirmwareError, match="after the end"):
        firmware.parse_ihex(":00000001FF\n" + rec(0, [1]))


def test_inspect_reports_kind_without_raising(tmp_path):
    assert firmware.inspect(tmp_path / "nope.elf")["error"] == "file not found"
    b = tmp_path / "a.bin"
    b.write_bytes(b"1234")
    i = firmware.inspect(b)
    assert i["kind"] == "bin" and i["size"] == 4 and len(i["sha8"]) == 8 and "error" not in i
    t = tmp_path / "a.txt"
    t.write_text("x")
    assert "must be" in firmware.inspect(t)["error"]
    e = tmp_path / "bad.elf"
    e.write_bytes(b"not an elf at all")
    assert "error" in firmware.inspect(e)
    h = tmp_path / "a.hex"
    h.write_text(rec(0, [0x08, 0x00], 4) + "\n" + rec(0, [1, 2]) + "\n:00000001FF\n")
    assert firmware.inspect(h)["flash"] == [0x08000000, 0x08000001]


def test_bin_needs_an_address(tmp_path):
    b = tmp_path / "a.bin"
    b.write_bytes(b"1234")
    with pytest.raises(firmware.FirmwareError, match="address"):
        firmware.load_image(b)


def test_cube_version_and_status_with_a_fake_runner(tmp_path):
    exe = tmp_path / "STM32_Programmer_CLI.exe"
    exe.write_text("")
    ok = lambda a, **k: subprocess.CompletedProcess(a, 0, "STM32CubeProgrammer version: 2.20.0 \n", "")  # noqa: E731
    bad = lambda a, **k: subprocess.CompletedProcess(a, 0, "garbage", "")  # noqa: E731
    assert envcheck.cube_version(exe, ok) == "2.20.0" and envcheck.cube_version(exe, bad) is None
    s = envcheck.cube_status(str(exe), ok)
    assert s["ready"] and s["active"]["path"] == str(exe) and s["configured_ok"] and s["active"]["source"] == "settings"
    s = envcheck.cube_status(str(tmp_path / "missing.exe"), bad)
    assert not s["ready"] and s["active"] is None and not s["configured_ok"]


def test_stlink_scan_parsing():
    raw = {"devices": [
        {"Status": "OK", "Class": "USB", "FriendlyName": "USB Composite Device", "InstanceId": "USB\\VID_0483&PID_374E\\SER1"},
        {"Status": "OK", "Class": "USBDevice", "FriendlyName": "ST-Link Debug", "InstanceId": "USB\\VID_0483&PID_374E&MI_00\\6&1&0&0000"},
        {"Status": "OK", "Class": "Ports", "FriendlyName": "STMicroelectronics STLink Virtual COM Port (COM6)", "InstanceId": "USB\\VID_0483&PID_374E&MI_02\\6&1&0&0002"},
        {"Status": "OK", "Class": "USB", "FriendlyName": "USB Composite Device", "InstanceId": "USB\\VID_0483&PID_374B\\SER2"},
        {"Status": "Error", "Class": "USBDevice", "FriendlyName": "ST-Link Debug", "InstanceId": "USB\\VID_0483&PID_374B&MI_00\\6&2&0&0000"}],
        "drivers": [{"DeviceID": "USB\\VID_0483&PID_374E&MI_00\\6&1&0&0000", "DriverProviderName": "STMicroelectronics", "DriverVersion": "2.2.0.0", "InfName": "oem64.inf"}],
        "packages": "Original Name:      stlink_dbg_winusb.inf"}
    r = envcheck.parse_stlink(raw, {"SER1": "robot"})
    by = {p["serial"]: p for p in r["probes"]}
    assert by["SER1"]["ready"] and by["SER1"]["target"] == "robot" and by["SER1"]["vcp"] == "COM6" and by["SER1"]["driver"] == ["STMicroelectronics 2.2.0.0"]
    assert not by["SER2"]["ready"] and by["SER2"]["problems"]
    assert r["ready"] is False and r["reason"] == "driver_problem" and r["packages"]
    none = envcheck.parse_stlink({"devices": [], "drivers": [], "packages": []})
    assert none == {"ready": False, "any": False, "probes": [], "packages": [], "reason": "no_probe"}
    assert envcheck.parse_stlink({"devices": raw["devices"][:3], "drivers": [], "packages": []})["ready"] is True


def test_claude_status_and_login_use_the_bundled_cli(tmp_path, monkeypatch):
    exe = tmp_path / "claude.exe"
    exe.write_text("")
    monkeypatch.setattr(envcheck, "claude_exe", lambda: exe)
    st = envcheck.claude_status(lambda a, **k: subprocess.CompletedProcess(a, 0, json.dumps({"loggedIn": False}), ""))
    assert st["sdk"] is True and st["logged_in"] is False
    calls = []
    assert envcheck.start_claude_login(lambda a, **k: calls.append((a, k))) == {"started": True}
    assert calls[0][0][1:] == ["auth", "login"]
    monkeypatch.setattr(envcheck, "claude_exe", lambda: None)
    assert envcheck.start_claude_login()["started"] is False and envcheck.claude_status()["sdk"] is False


def test_file_dialog_uses_powershell_with_kind_in_the_environment():
    seen = []

    def runner(args, **k):
        seen.append((args, k["env"]))
        return subprocess.CompletedProcess(args, 0, 'noise\n{"path":"C:\\\\x\\\\app.hex"}\n', "")

    assert envcheck.pick_file("firmware", None, runner) == {"path": "C:\\x\\app.hex"}
    args, env = seen[0]
    assert args[0] == "powershell" and "-STA" in args and env["RDT_DLG_KIND"] == "firmware"
    assert "firmware" not in args[-1].split("$filters")[0]            # the kind is data, not part of the script text
    assert envcheck.pick_file("rm -rf", None, runner)["path"] is None and len(seen) == 1   # unknown kind: no process
    bad = lambda a, **k: subprocess.CompletedProcess(a, 1, "", "boom")  # noqa: E731
    assert envcheck.pick_file("elf", None, bad)["path"] is None

def test_pinned_cube_version_matches_toolchain_file():
    from pathlib import Path
    ps = (Path(__file__).parents[1] / "scripts" / "toolchain.psd1").read_text(encoding="utf-8")
    assert "CubeProgrammerVersion" in ps and envcheck.PINNED_CUBE in ps
