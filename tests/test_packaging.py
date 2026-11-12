import re
from pathlib import Path

import pytest

import rdt
from rdt import paths

ROOT = Path(__file__).parents[1]


def test_version_matches_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "%s"$' % re.escape(rdt.__version__), text, re.M)


def test_pyproject_is_valid_toml_without_bom():
    import tomllib
    raw = (ROOT / "pyproject.toml").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert tomllib.loads(raw.decode("utf-8"))["project"]["name"] == "robot-diag"


def test_installed_app_keeps_user_data_outside_the_bundle(tmp_path, monkeypatch):
    res, data = tmp_path / "bundle", tmp_path / "appdata" / "RobotDiag"
    res.mkdir()
    (res / "targets.yaml").write_text("targets: {}\n", encoding="utf-8")
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "RESOURCES", res)
    monkeypatch.setattr(paths, "DATA", data)
    paths.ensure_data()
    assert (data / "targets.yaml").read_text(encoding="utf-8") == "targets: {}\n"
    (data / "targets.yaml").write_text("targets: {edited: 1}\n", encoding="utf-8")
    paths.ensure_data()                                                   # never overwrites the user's copy
    assert "edited" in (data / "targets.yaml").read_text(encoding="utf-8")


def test_source_checkout_uses_the_repository(monkeypatch):
    assert paths.FROZEN is False and paths.DATA == ROOT and paths.UI_DIST == ROOT / "ui" / "dist"


def test_build_files_are_consistent():
    spec = (ROOT / "scripts" / "robot_diag.spec").read_text(encoding="utf-8")
    assert "rdt" in spec and "rdt_entry.py" in spec and "ui" in spec and "claude_agent_sdk" in spec and "pyocd" in spec
    iss = (ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss and "RobotDiag.exe" in iss and "{localappdata}" in iss
    ps = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert "robot_diag.spec" in ps and "installer.iss" in ps and "smoke" in ps.lower()
    assert (ROOT / "scripts" / "robot_diag.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_launcher_defaults_to_the_native_window(monkeypatch):
    from rdt import launcher
    seen = []
    monkeypatch.setattr("rdt.cli.main", lambda argv=None: seen.append(argv) or 0)
    monkeypatch.setattr("sys.argv", ["RobotDiag.exe"])
    assert launcher.main() == 0 and seen == [["app"]]
    monkeypatch.setattr("sys.argv", ["RobotDiag.exe", "serve", "--port", "1"])
    launcher.main()
    assert seen[-1] == ["serve", "--port", "1"]


@pytest.mark.skipif(not (ROOT / "dist" / "RobotDiag" / "RobotDiag.exe").exists(), reason="exe not built")
def test_built_exe_folder_has_the_bundled_pieces():
    d = ROOT / "dist" / "RobotDiag"
    assert (d / "_internal" / "ui" / "dist" / "index.html").exists() and (d / "_internal" / "targets.yaml").exists()
