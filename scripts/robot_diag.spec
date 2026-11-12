# PyInstaller spec for the installed app (one-folder build): dist/RobotDiag/RobotDiag.exe
# Built by scripts/build_exe.ps1. Entry: scripts/rdt_entry.py -> rdt/launcher.py (native window by default; `RobotDiag.exe serve --port N` is the headless daemon).
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "ui" / "dist"), "ui/dist"), (str(ROOT / "targets.yaml"), ".")]
binaries, hidden = [], []

# Packages with data files, native libraries or plugins found at run time (pyOCD loads probe and target plugins by entry point,
# the Agent SDK ships its own claude.exe, pywebview + pythonnet need their .NET glue).
for pkg in ("pyocd", "libusb_package", "cmsis_pack_manager", "usb", "hid", "pylink", "claude_agent_sdk", "webview", "clr_loader", "pythonnet",
            "serial", "elftools", "capstone", "intelhex", "intervaltree", "natsort", "prettytable"):
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:  # a missing optional package must not stop the build; the smoke test shows what is really needed
        print(f"spec: skipping {pkg}: {e}")
        continue
    datas += d; binaries += b; hidden += h

hidden += collect_submodules("uvicorn") + collect_submodules("rdt") + collect_submodules("websockets") + collect_submodules("anyio")
hidden += ["httptools", "watchfiles", "yaml", "clr"]
for dist in ("pyocd", "claude-agent-sdk", "pywebview", "pythonnet", "libusb-package", "cmsis-pack-manager", "fastapi", "starlette",
             "uvicorn", "pydantic", "pydantic-core", "anyio", "sse-starlette"):
    try:
        datas += copy_metadata(dist)
    except Exception as e:
        print(f"spec: no metadata for {dist}: {e}")

a = Analysis(
    [str(ROOT / "scripts" / "rdt_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "matplotlib", "numpy.tests", "IPython", "notebook", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="RobotDiag",
    console=False,                 # windowed: output goes to %LOCALAPPDATA%\RobotDiag\logs\robot_diag.log (rdt/launcher.py)
    icon=str(ROOT / "scripts" / "robot_diag.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RobotDiag")
