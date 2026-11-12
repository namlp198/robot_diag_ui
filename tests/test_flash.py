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


def test_only_elf_files(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"\0" * 8)
    with pytest.raises(FlashError, match="elf"):
        mk(image=f)


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
