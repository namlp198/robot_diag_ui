"""Checks of the machine the tool runs on, for the Settings page: STM32_Programmer_CLI, ST-LINK drivers, Claude login,
and a native file dialog. Nothing here touches a board: probes are only looked up in the Windows device list.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PINNED_CUBE = "2.20.0"  # scripts/toolchain.psd1 (CubeProgrammer); a different version works but is reported
CUBE_EXE = "STM32_Programmer_CLI.exe"
DEFAULT_CUBE = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin") / CUBE_EXE
CUBE_GLOBS = [  # other places the tool lives: a standalone install, CubeIDE's bundled copy
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer*\bin\STM32_Programmer_CLI.exe",
    r"C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*\tools\bin\STM32_Programmer_CLI.exe",
]
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


# --- STM32_Programmer_CLI --------------------------------------------------------------------------------------------------
def cube_version(exe: Path, runner=subprocess.run) -> str | None:
    try:
        r = runner([str(exe), "--version"], capture_output=True, text=True, timeout=20,
                   creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"STM32CubeProgrammer version:\s*([\d.]+)", (r.stdout or "") + (r.stderr or ""))
    return m.group(1) if m else None


def cube_candidates(configured: str | None) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []

    def add(p, src):
        p = Path(p)
        if p.is_file() and p.name.lower() == CUBE_EXE.lower() and all(p != q for q, _ in found):
            found.append((p, src))

    if configured:
        add(configured, "settings")
    w = shutil.which("STM32_Programmer_CLI")
    if w:
        add(w, "PATH")
    add(DEFAULT_CUBE, "default install")
    for pat in CUBE_GLOBS:
        for p in sorted(glob.glob(pat), reverse=True):
            add(p, "CubeIDE bundled" if "plugins" in p else "CubeProgrammer install")
    return found


def cube_status(configured: str | None, runner=subprocess.run) -> dict:
    cands = []
    for p, src in cube_candidates(configured):
        cands.append({"path": str(p), "source": src, "version": cube_version(p, runner)})
    usable = [c for c in cands if c["version"]]
    active = usable[0] if usable else None
    return {"ready": active is not None, "active": active, "pinned": PINNED_CUBE, "candidates": cands,
            "configured": configured or None,
            "configured_ok": bool(configured) and any(c["path"].lower() == configured.lower() and c["version"] for c in cands)}


# --- ST-LINK drivers ---------------------------------------------------------------------------------------------------------
_PS = r"""
$d = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0483' } |
  Select-Object Status, Class, FriendlyName, InstanceId)
$v = @(Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Where-Object { $_.DeviceID -match 'VID_0483' } |
  Select-Object DeviceID, DriverProviderName, DriverVersion, InfName)
$p = @((pnputil /enum-drivers 2>$null) | Select-String -Pattern 'Original Name' | ForEach-Object { $_.Line.Trim() } | Where-Object { $_ -match 'stlink|st-link' })
@{ devices = $d; drivers = $v; packages = $p } | ConvertTo-Json -Depth 3 -Compress
"""
PID_NAMES = {"374B": "ST-LINK/V2-1", "374E": "ST-LINK/V3E", "374F": "ST-LINK/V3S", "3753": "ST-LINK/V3", "3748": "ST-LINK/V2", "3744": "ST-LINK/V1"}


def _list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def parse_stlink(raw: dict, targets: dict[str, str] | None = None) -> dict:
    """`raw`: the JSON of the PowerShell query. `targets`: serial -> target name (targets.yaml)."""
    targets = targets or {}
    devices, drivers = _list(raw.get("devices")), _list(raw.get("drivers"))
    probes: dict[str, dict] = {}
    for d in devices:  # top-level composite device: USB\VID_0483&PID_xxxx\<serial>
        m = re.match(r"USB\\VID_0483&PID_([0-9A-F]{4})\\(.+)$", d["InstanceId"], re.I)
        if m:
            probes[m.group(1).upper()] = {"pid": m.group(1).upper(), "serial": m.group(2), "status": d["Status"], "debug": None, "vcp": None, "problems": []}
    for d in devices:
        m = re.match(r"USB\\VID_0483&PID_([0-9A-F]{4})&MI_(\d\d)\\", d["InstanceId"], re.I)
        if not m or m.group(1).upper() not in probes:
            continue
        p = probes[m.group(1).upper()]
        name = d.get("FriendlyName") or ""
        if re.search(r"st-?link debug", name, re.I) or m.group(2) == "00":
            p["debug"] = d["Status"]
        com = re.search(r"\((COM\d+)\)", name)
        if com:
            p["vcp"] = com.group(1)
        if d["Status"] != "OK":
            p["problems"].append(f"{name}: {d['Status']}")
    out = []
    for p in probes.values():
        provs = {(v.get("DriverProviderName"), v.get("DriverVersion")) for v in drivers
                 if f"PID_{p['pid']}" in v["DeviceID"].upper() and "STMicroelectronics" in (v.get("DriverProviderName") or "")}
        p["driver"] = sorted(f"{a} {b}" for a, b in provs)
        p["name"] = PID_NAMES.get(p["pid"], f"ST-LINK (PID {p['pid']})")
        p["target"] = targets.get(p["serial"])
        p["ready"] = p["status"] == "OK" and p["debug"] == "OK"
        out.append(p)
    ready = bool(out) and all(p["ready"] for p in out)
    return {"ready": ready, "any": bool(out), "probes": out, "packages": [str(x) for x in _list(raw.get("packages"))],
            "reason": None if ready else ("no_probe" if not out else "driver_problem")}


def scan_stlink(targets: dict[str, str] | None = None, runner=subprocess.run) -> dict:
    if os.name != "nt":
        return {"ready": False, "any": False, "probes": [], "packages": [], "reason": "unsupported_os"}
    try:
        r = runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], capture_output=True, text=True, timeout=60,
                   creationflags=CREATE_NO_WINDOW)
        raw = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"ready": False, "any": False, "probes": [], "packages": [], "reason": f"scan_failed: {str(e)[:100]}"}
    return parse_stlink(raw, targets)


# --- Claude login ------------------------------------------------------------------------------------------------------------
def claude_exe() -> Path | None:
    try:
        import claude_agent_sdk
    except ImportError:
        return None
    p = Path(claude_agent_sdk.__file__).parent / "_bundled" / ("claude.exe" if os.name == "nt" else "claude")
    return p if p.exists() else None


def claude_status(runner=subprocess.run) -> dict:
    exe = claude_exe()
    if exe is None:
        return {"sdk": False, "logged_in": None}
    v = {"sdk": True, "logged_in": None}
    try:
        r = runner([str(exe), "auth", "status"], capture_output=True, text=True, timeout=20,
                   creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
        j = json.loads(r.stdout)
        v["logged_in"] = bool(j.get("loggedIn"))
        v["method"] = j.get("authMethod")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return v


def start_claude_login(popen=subprocess.Popen) -> dict:
    """Runs `claude auth login` of the bundled Claude Code in its own console window (it opens the browser and may ask
    to paste a code there). The login belongs to the user: the app never sees the credentials."""
    exe = claude_exe()
    if exe is None:
        return {"started": False, "error": "claude-agent-sdk is not installed"}
    try:
        popen([str(exe), "auth", "login"], creationflags=CREATE_NEW_CONSOLE if os.name == "nt" else 0)
    except OSError as e:
        return {"started": False, "error": str(e)}
    return {"started": True}


# --- native file dialog ------------------------------------------------------------------------------------------------------
# A Windows "Open file" dialog from PowerShell (WinForms), so it works from source and from the installed exe alike (sys.executable
# is the app itself there). Kind and start folder go in through environment variables, never into the script text.
_DIALOG = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$filters = @{
  elf      = 'ELF files (*.elf;*.axf;*.out)|*.elf;*.axf;*.out|All files (*.*)|*.*'
  firmware = 'Firmware (*.elf;*.hex;*.bin)|*.elf;*.hex;*.bin|ELF (*.elf)|*.elf|Intel HEX (*.hex)|*.hex|Binary (*.bin)|*.bin|All files (*.*)|*.*'
  exe      = 'STM32_Programmer_CLI.exe|STM32_Programmer_CLI.exe|Programs (*.exe)|*.exe'
}
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.StartPosition = 'CenterScreen'; $owner.Opacity = 0
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Show()
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Title = 'Select a file'
$d.Filter = $filters[$env:RDT_DLG_KIND]
if ($env:RDT_DLG_INITIAL -and (Test-Path -LiteralPath $env:RDT_DLG_INITIAL)) { $d.InitialDirectory = $env:RDT_DLG_INITIAL }
$path = $null
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $path = $d.FileName }
$owner.Close()
@{ path = $path } | ConvertTo-Json -Compress
"""


def pick_file(kind: str, initial: str | None = None, runner=subprocess.run) -> dict:
    if kind not in ("elf", "firmware", "exe"):
        return {"path": None, "error": "bad kind"}
    start = ""
    if initial and Path(initial).exists():
        start = str(Path(initial).parent if Path(initial).is_file() else initial)
    env = {**os.environ, "RDT_DLG_KIND": kind, "RDT_DLG_INITIAL": start}
    try:
        r = runner(["powershell", "-STA", "-NoProfile", "-NonInteractive", "-Command", _DIALOG], capture_output=True, text=True,
                   timeout=600, env=env, creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        return {"path": None, "error": f"dialog failed: {str(e)[:120]}"}