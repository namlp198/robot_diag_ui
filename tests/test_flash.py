from pathlib import Path
from types import SimpleNamespace

import pytest

from rdt import flash
from rdt.flash import FlashError

REPOS = Path(__file__).parents[2]  # the repositories folder
ROOT = REPOS / "robot_diag_ui"      # targets.yaml paths are relative to this
ELF = REPOS / "robot_rc_rtos/SFF_Debug/robot_rc_rtos.elf"
pytestmark = pytest.mark.skipif(not ELF.exists(), reason="remote ELF not built")

CFG = {"probe_serial": "S", "mcu": "STM32F446", "dev_id": 0x421, "idcode_addr": 0xE0042000,
       "flash_range": [0x08000000, 0x0807FFFF], "allowed_images": ["../robot_rc_rtos/SFF_*/*.elf"]}


def board(dev=0x421):
    return lambda addr, n: (dev | 0x10000000).to_bytes(4, "little")[:n] if addr == 0xE0042000 else b"\xff" * n


def mk(cfg=CFG, read=board(), attached=lambda s: True, image=ELF):
    return flash.plan("remote", cfg, image, ROOT, read, attached)


def test_good_plan_has_confirm_phrase_and_command():
    p = mk()
    assert p.ok and p.confirm == f"FLASH remote {p.sha256[:8]}"
    assert p.command[0].endswith("STM32_Programmer_CLI.exe") and "-w" in p.command and "-v" in p.command
    assert "sn=S" in p.command and p.already_flashed is False


@pytest.mark.parametrize("kw,failed", [
    ({"read": board(0x450)}, "board_dev_id"),                    # wrong MCU on the probe
    ({"read": None}, "board_dev_id"),                           # unreadable board fails closed
    ({"attached": lambda s: False}, "probe_attached"),
    ({"cfg": {**CFG, "allowed_images": ["../robot_att/*/*.elf"]}}, "image_allowed_for_target"),
    ({"cfg": {**CFG, "flash_range": [0x08100000, 0x081FFFFF]}}, "image_inside_flash_range"),
])
def test_failed_checks_refuse_plan(kw, failed):
    p = mk(**kw)
    assert not p.ok and failed in [c.name for c in p.checks if not c.ok]


def test_only_known_firmware_file_types(tmp_path):
    for name in ("x.txt", "x.zip", "x"):
        f = tmp_path / name
        f.write_bytes(b"\0" * 8)
        with pytest.raises(FlashError, match="elf, .hex or .bin"):
            mk(image=f)


def hex_record(addr, data, typ=0):
    b = bytes([len(data), addr >> 8, addr & 0xFF, typ]) + bytes(data)
    return ":" + (b + bytes([(-sum(b)) & 0xFF])).hex().upper()


def write_hex(path, base, data):
    lines = [hex_record(0, base.to_bytes(4, "big")[:2], 4), hex_record(base & 0xFFFF, data), ":00000001FF"]
    path.write_text("\n".join(lines) + "\n")


def test_unregistered_bin_or_hex_is_refused_registered_one_is_planned(tmp_path):
    b = tmp_path / "app.bin"
    b.write_bytes(bytes(range(64)))
    p = mk(image=b)
    assert not p.ok and "image_allowed_for_target" in [c.name for c in p.checks if not c.ok]
    p = flash.plan("remote", CFG, b, ROOT, board(), lambda s: True, extra_allowed=[b])
    assert p.ok and p.kind == "bin" and p.address == 0x08000000
    assert p.command[-4:] == [str(b), "0x08000000", "-v", "-rst"] or p.command[p.command.index("-w") + 2] == "0x08000000"
    p = flash.plan("remote", CFG, b, ROOT, board(), lambda s: True, extra_allowed=[b], address=0x08020000)
    assert p.ok and "0x08020000" in p.command
    h = tmp_path / "app.hex"
    write_hex(h, 0x08000000, bytes(range(32)))
    p = flash.plan("remote", CFG, h, ROOT, board(), lambda s: True, extra_allowed=[h])
    assert p.ok and p.kind == "hex" and p.segments == [(0x08000000, 32)] and "0x" not in " ".join(p.command[p.command.index("-w") + 2:])


def test_bin_and_hex_outside_flash_or_misaligned_fail(tmp_path):
    b = tmp_path / "a.bin"
    b.write_bytes(b"\x01" * 64)
    far = flash.plan("remote", CFG, b, ROOT, board(), lambda s: True, extra_allowed=[b], address=0x08100000)
    assert not far.ok and "image_inside_flash_range" in [c.name for c in far.checks if not c.ok]
    odd = flash.plan("remote", CFG, b, ROOT, board(), lambda s: True, extra_allowed=[b], address=0x08000002)
    assert not odd.ok
    h = tmp_path / "bad.hex"
    h.write_text(":020000040800F2\n:04000000DEADBEEF00\n:00000001FF\n")  # wrong checksum
    assert not flash.plan("remote", CFG, h, ROOT, board(), lambda s: True, extra_allowed=[h]).ok


def test_bin_flash_is_verified_against_its_own_bytes(tmp_path):
    from rdt import firmware
    b = tmp_path / "a.bin"
    data = bytes(range(256)) * 2
    b.write_bytes(data)
    p = flash.plan("remote", CFG, b, ROOT, lambda a, n: data[a - 0x08000000:a - 0x08000000 + n] if 0x08000000 <= a < 0x08000200 else (0x421).to_bytes(4, "little")[:n], lambda s: True, extra_allowed=[b])
    assert p.already_flashed is True
    assert firmware.load_image(b, 0x08000000)[0][0] == 0x08000000


def run(p, **kw):
    calls = []

    def runner(cmd, **k):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="Download verified successfully", stderr="")

    args = dict(confirm=p.confirm, motors_safe=False, repo_root=ROOT, log_dir=kw.pop("log_dir"), runner=runner)
    args.update(kw)
    return flash.run(p, CFG, **args), calls


def test_run_needs_exact_confirmation_and_logs(tmp_path):
    p = mk()
    with pytest.raises(FlashError, match="exactly"):
        run(p, log_dir=tmp_path, confirm="yes")
    res, calls = run(p, log_dir=tmp_path)
    assert res["programmed"] and len(calls) == 1
    assert (tmp_path / "flash_log.jsonl").read_text().count("\n") == 1


def test_robot_style_target_needs_motors_safe(tmp_path):
    p = mk()
    p.needs_motors_safe = True
    with pytest.raises(FlashError, match="safe"):
        run(p, log_dir=tmp_path, motors_safe=False)
    res, _ = run(p, log_dir=tmp_path, motors_safe=True)
    assert res["programmed"]


def test_failed_plan_never_reaches_the_runner(tmp_path):
    p = mk(read=board(0x450))
    with pytest.raises(FlashError, match="failed checks"):
        run(p, log_dir=tmp_path, confirm=p.confirm)


def test_image_changed_after_plan_is_refused(tmp_path):
    p = mk()
    p.sha256 = "0" * 64
    with pytest.raises(FlashError, match="changed"):
        run(p, log_dir=tmp_path, confirm=p.confirm)


def test_post_flash_probe_is_released(tmp_path):
    closed = []

    class FakeProbe:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            closed.append(True)

        def read(self, addr, n):
            return bytes([255]) * n

    p = mk()
    res, _ = run(p, log_dir=tmp_path, read_after=FakeProbe)
    assert closed == [True] and res["verified_after"] is False  # 0xFF flash does not match the image
