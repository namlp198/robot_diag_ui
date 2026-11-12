# robot_diag_ui: build, package and deploy guide

From a blank machine to an installer that runs on another one. Vietnamese version: [BUILD_DEPLOY.vi.md](BUILD_DEPLOY.vi.md).
All commands are PowerShell, run from the repository root (`robot_diag_ui`) unless stated otherwise.

## 1. Overview: three ways to run

| Way | Use it for | Needs on the machine |
|---|---|---|
| **From source** (`rdt serve`, `scripts\start.ps1`) | development, tests | Python 3.12, Node (to build the UI), pip packages |
| **Packaged folder** `dist\RobotDiag\RobotDiag.exe` | trying a build before release | Windows + WebView2 only |
| **Installer** `RobotDiag-Setup-<version>.exe` | handing it to users / other machines | Windows + WebView2 only |

The architecture is the same in all three: one daemon (`rdt`, FastAPI, listening on `127.0.0.1` only) owns the ST-LINK probes and serves the
web UI (Svelte, prebuilt into `ui\dist`). The app window (`rdt app`) is pywebview on Microsoft Edge WebView2; a normal browser opens the same
address. The daemon is the only program holding a probe, and a probe serves one session at a time (close a CubeIDE debug session before reading).

```
rdt/            Python code (daemon, CLI, SWD reads, analysis, flashing, chat)
ui/             Svelte + Vite UI  ->  ui/dist (built)
targets.yaml    the two boards (ST-LINK serials, ELF files, flash ranges)
scripts/        start.ps1, check.ps1, build_exe.ps1, robot_diag.spec, installer.iss, ...
tests/          pytest
docs/ decisions/ handoff/ tasks/   documentation, decision records, handoff
```

## 2. Requirements

**Development / build machine** (Windows 10/11 x64):

| Component | Version | Note |
|---|---|---|
| Python | 3.12 | pinned in `scripts\toolchain.psd1` |
| Node.js | 17.x or newer (17.9.1 used) | only to build the UI; Vite 4.5.5 and Svelte 4.2.19 were chosen because they run on Node 17 |
| Inno Setup | 6 (`ISCC.exe`) | only for the installer; `winget install JRSoftware.InnoSetup` |
| STM32CubeProgrammer | 2.20.0 | only for flashing and the Programmer CLI page |
| ST-LINK driver | ST's STSW-LINK009 | to read real boards |

**End-user machine** (installer only): Windows 10/11, the **Edge WebView2 runtime** (part of Windows 11 and of current Edge), the ST-LINK
driver, STM32CubeProgrammer for flashing, and a Claude login for the chat. No Python, Node or Git needed.

## 3. Development setup

```powershell
git clone https://github.com/namlp198/robot_diag_ui.git
cd robot_diag_ui
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev,daemon,probe,chat,app]
.venv\Scripts\python -m pip install pyinstaller==6.22.3      # only for packaging
cd ui; npm install; npm run build; cd ..                      # creates ui\dist
.\scripts\check.ps1                                           # pytest + CLI smoke test
```

Extras in `pyproject.toml`:

| Extra | Contents | Needed for |
|---|---|---|
| (default) | pyelftools, pyyaml | reading ELF files, configuration |
| `dev` | pytest | tests |
| `daemon` | fastapi, uvicorn, httpx | the daemon and the UI |
| `probe` | pyocd 0.46.1, pyserial | SWD reads, VCP log |
| `chat` | claude-agent-sdk 0.2.180 | the Claude chat |
| `app` | pywebview 6.2.1 | the native window (`rdt app`) |

Pinned versions live in `scripts\toolchain.psd1`; changing one needs a note in `decisions\` (repository rule).

Firmware: `targets.yaml` points relatively to the sibling repositories (`..\robot_s_rtos`, `..\robot_rc_rtos`). Build the firmware in CubeIDE first to get
the `.elf` files (the Debug build has DWARF for naming variables; Release is only needed for addresses).

## 4. Run and check

```powershell
.\scripts\start.ps1              # native window (rdt app); closing the window stops the daemon
.\scripts\start.ps1 -Edge        # Edge app window (automatic fallback when pywebview is missing)
.\scripts\start.ps1 -Browser     # browser tab; stop with Ctrl+C
.\scripts\make_shortcut.ps1      # "Robot Diag" shortcut on the desktop
.venv\Scripts\rdt serve          # daemon only, UI at http://127.0.0.1:8765
.venv\Scripts\rdt --help         # watch, record, replay, analyze, sweep, flash-plan, resolve, serve, app
```

`start.ps1` compares the code's modification time with the running daemon and restarts a daemon older than the code (a stale daemon serves the
new UI with old endpoints, which leaves pages like Frames empty).

Before a commit or a build:

```powershell
.\scripts\check.ps1                                  # pytest + rdt --help
$env:RDT_HW_TESTS = "1"; .venv\Scripts\python -m pytest   # adds the tests that use a real probe (close CubeIDE debug first)
.venv\Scripts\python -I scripts\gen_reference.py     # regenerate docs\REFERENCE.*.md after editing rdt\reference.py
```

Tests that need an ELF or a probe skip, never fail, when it is absent. Tests also check that every variable the UI shows is in the reference
documentation and that the generated documents are not stale.

Optional environment: `RDT_CHAT_MODEL` (default `claude-sonnet-5-5`), `RDT_CHAT_MAX_USD` (chat cost cap, default 2.0). Model, effort and cap can
also be set on the Settings page.

## 5. Build the UI

```powershell
cd ui
npm install        # first time
npm run build      # produces ui\dist (static files served by the daemon)
npm run dev        # optional: Vite dev server while editing the UI
```

`ui\dist` is not in git. The daemon reads it when run from source; the packaged app embeds the built copy.

## 6. Package as .exe and installer

```powershell
.\scripts\build_exe.ps1
```

One command, in order:

1. Builds the UI (`npm run build`) unless `-SkipUi`.
2. **PyInstaller** (`scripts\robot_diag.spec`, one-folder, windowed) produces `dist\RobotDiag\RobotDiag.exe` (about 420 MB: with pyOCD, the Agent SDK's
   `claude.exe`, pywebview and the UI) unless `-SkipBuild`.
3. **Smoke test** of the built exe: runs `RobotDiag.exe serve --port 8897` and checks that the UI is served, the API answers, the Claude SDK is bundled
   and the ST-LINK scan runs (`-NoSmoke` skips it).
4. **Inno Setup** (`scripts\installer.iss`) produces `dist\installer\RobotDiag-Setup-<version>.exe` (about 180 MB) unless `-NoInstaller`.

| Option | Effect |
|---|---|
| `-SkipUi` | reuse `ui\dist` (no npm) |
| `-SkipBuild` | reuse `dist\RobotDiag` (smoke test and installer only) |
| `-NoSmoke` | skip the smoke test |
| `-NoInstaller` | build the folder only |

The first build takes several minutes (PyInstaller collects pyOCD, the SDK and pywebview). `dist\` and `build\` are git-ignored.

Files involved:

| File | Role |
|---|---|
| `scripts\rdt_entry.py` | PyInstaller entry point; absolute imports (PyInstaller runs its entry file as a top-level script, where relative imports fail) |
| `rdt\launcher.py` | no arguments: open the window (`rdt app`); with arguments: behave like the `rdt` command (e.g. `RobotDiag.exe serve --port 8765`); logs to a file |
| `rdt\paths.py` | separates the read-only bundle from the user's data folder |
| `scripts\robot_diag.spec` | which packages need `collect_all` (pyOCD, libusb, claude_agent_sdk, webview, pythonnet...) and metadata |
| `scripts\installer.iss` | the Inno Setup installer |
| `scripts\robot_diag.ico`, `scripts\make_icon.py` | the icon and the script that generates it |

### Version

The version is in two places that must be equal: `rdt\__init__.py` (`__version__`) and `pyproject.toml` (`version`). A test checks it; the installer
takes its number from `rdt.__version__`.

## 7. The installer

- Per-user install, **no administrator rights**: the app goes to `%LOCALAPPDATA%\Programs\RobotDiag`, with a Start menu entry and an optional desktop shortcut.
- Silent install: `RobotDiag-Setup-0.2.0.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES` (add `/DIR="D:\Apps\RobotDiag"` to change the folder,
  `/TASKS="desktopicon"` for the desktop shortcut).
- Upgrade: run a newer installer over the old one (same `AppId`); user data is not touched.
- Uninstall: Settings > Apps, or `%LOCALAPPDATA%\Programs\RobotDiag\unins000.exe /VERYSILENT`. **User data is not removed** (section 8); delete that
  folder by hand for a completely clean machine.
- At the end the installer warns if the Edge WebView2 runtime is missing (get the Evergreen runtime from Microsoft's WebView2 page).

## 8. Data and configuration on an installed machine

The installed app **never writes into its install folder**. Everything the user changes lives in `%LOCALAPPDATA%\RobotDiag`:

| Path | Contents |
|---|---|
| `targets.yaml` | board configuration (copied from the bundled default on first run, never overwritten afterwards) |
| `sessions\` | recorded sessions, `flash_log.jsonl`, `settings.json` |
| `sessions\chats\` | saved chat conversations (with attached images and files) |
| `logs\robot_diag.log` | application log (the exe has no console) |
| `%LOCALAPPDATA%\robot_diag_ui\webview` | WebView profile (theme, language, Live Expressions list) |

Backup: copy `%LOCALAPPDATA%\RobotDiag`. When run from source these live in the repository itself (`sessions\` is git-ignored).

## 9. Deploying to a new machine (checklist)

1. Install the **ST-LINK driver** (STSW-LINK009) and **STM32CubeProgrammer 2.20.0** (for flashing). Plug in the boards.
2. Run `RobotDiag-Setup-*.exe` and open Robot Diag.
3. Open **Settings > Environment and tools** and scan: STM32_Programmer_CLI must say *Ready*, the ST-LINK driver *Ready* with each probe and its
   serial listed; Claude *Ready*, otherwise press the `claude auth login` button and log in in the browser.
4. **Probe serials**: `targets.yaml` holds the ST-LINK serials of the current pair of boards. For other boards edit
   `%LOCALAPPDATA%\RobotDiag\targets.yaml` (`probe_serial`) with the serials shown in step 3. There is no UI for this yet.
5. **ELF files**: the machine does not have the firmware repositories next to it, so the paths in `targets.yaml` do not exist. Go to
   **Settings > ELF files**, add each board's ELF (the Debug build with DWARF for variables, plus the Release ELF as the image if the board runs Release) and choose them.
6. **Files to flash**: **Settings > Firmware files to flash**, register `.elf`/`.hex`/`.bin` per board (a `.bin` needs an address). The Flash panel
   only accepts registered files.
7. Try reading: press "Start reading" on the Dashboard; each board's status and whether the firmware matches the ELF show at the top.
8. Before flashing the robot: wheels off the ground, someone at the robot ready to cut power (motor power is the board's supply).

## 10. Release procedure

1. Update the code, run `.\scripts\check.ps1` (must be green).
2. If displayed variables or `rdt\reference.py` changed: `python -I scripts\gen_reference.py`.
3. Raise the version in `rdt\__init__.py` and `pyproject.toml`.
4. `.\scripts\build_exe.ps1` (the smoke test must pass).
5. **Install the installer on a clean machine** (no Python, no firmware repositories): install, open, go through steps 3 to 7 of section 9, uninstall,
   install again (upgrade) and check that user data is intact.
6. Record in `handoff\latest.md` what was verified and what was not and, if the architecture changed, add a file in `decisions\`.
7. Commit, tag the version, store `RobotDiag-Setup-<version>.exe` where releases are kept (it is not in git).

The installer is **not code-signed**: Windows SmartScreen warns on first run on other machines ("Run anyway"). To avoid it, sign with a code signing
certificate after the build, for example `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /a dist\installer\RobotDiag-Setup-<version>.exe`
(and sign `RobotDiag.exe` before building the installer). This has not been done.

## 11. Updating pinned dependencies

1. Change the version in `pyproject.toml` and `scripts\toolchain.psd1` (a test checks they agree with this document).
2. `.venv\Scripts\python -m pip install -e .[...]`, run `check.ps1`, then rebuild and run the smoke test: PyInstaller breaks easily when a package changes how
   it loads plugins or data (pyOCD loads probes by entry point, the Agent SDK ships `claude.exe`, pywebview needs pythonnet).
3. Record the reason in `decisions\`.

## 12. Troubleshooting

| Symptom | Usual cause | Fix |
|---|---|---|
| `Access denied (insufficient permissions)` when reading | the probe is held by another program (CubeIDE debug, a second daemon) | stop the debug session, close the extra daemon, replug the ST-LINK |
| Frames and Live Expressions empty after an update | an old daemon is still running the old code | close the window and run `start.ps1` again (it restarts an old daemon) |
| The window does not open / is slow the first time | WebView2 missing, or the first unpack is slow | install the WebView2 Evergreen runtime; wait a few seconds; see `logs\robot_diag.log` |
| "ELF file not found" on Start reading | `targets.yaml` points to paths that do not exist on this machine | choose the ELF in Settings > ELF files |
| `FIRMWARE MISMATCH` | the board runs another build than the chosen ELF | choose the right ELF (or reflash); values read meanwhile are not trustworthy |
| Chat says not logged in | the bundled Claude Code is not logged in | Settings > the `claude auth login` button |
| `pip install` or `pytest` says "Invalid statement (at line 1, column 1)" | `pyproject.toml` was rewritten with a BOM | save it as UTF-8 without BOM (do not use PowerShell 5.1 `Set-Content -Encoding utf8`) |
| `build_exe.ps1` stops at PyInstaller with `NativeCommandError` | PowerShell 5.1 treats stderr as an error | the script wraps tools in `Invoke-Tool`; for your own calls set `$ErrorActionPreference = "Continue"` around the command |
| The exe exits at once (code 1), no log | an import error at startup | run `RobotDiag.exe serve --port 8899` and read `%LOCALAPPDATA%\RobotDiag\logs\robot_diag.log`; check `build\pyinstaller\robot_diag\warn-robot_diag.txt` |
| Smoke test says the SDK is not bundled | the `claude_agent_sdk` package was not collected | check `collect_all("claude_agent_sdk")` in `robot_diag.spec` |
| pytest hangs listing USB | CubeIDE holds a session | probe tests run only with `RDT_HW_TESTS=1`; close CubeIDE debug |
| SmartScreen warns about the installer | it is not signed | choose "More info" > "Run anyway", or sign it (section 10) |

## 13. Security and operating safety

- The daemon listens on `127.0.0.1` only and rejects non-local Host/Origin headers.
- **Read-only by default**: no halt, no reset, no target memory write. The only thing that writes to a board is flashing through the "Flash firmware" panel
  (confirmation phrase, DEV_ID, flash range, registered file, `motors_safe` for the robot). Claude only has read and display tools.
- The robot's USART3 VCP is never opened (it is shared with the E22 receive path).
- Peripheral registers are readable only when "allow peripheral reads" is on in Settings (a read can clear a flag or take a byte out of a FIFO).
- Anything attached in the chat is sent to Anthropic like any chat message.

## 14. Quick command table

| Task | Command |
|---|---|
| Set up the environment | `python -m venv .venv; .venv\Scripts\python -m pip install -e .[dev,daemon,probe,chat,app]` |
| Build the UI | `cd ui; npm install; npm run build` |
| Run | `.\scripts\start.ps1` |
| Check | `.\scripts\check.ps1` |
| Build + installer | `.\scripts\build_exe.ps1` |
| Folder build only | `.\scripts\build_exe.ps1 -NoInstaller` |
| Rebuild the installer from an existing build | `.\scripts\build_exe.ps1 -SkipBuild -NoSmoke` |
| Silent install | `RobotDiag-Setup-<v>.exe /VERYSILENT /NORESTART` |
| Silent uninstall | `%LOCALAPPDATA%\Programs\RobotDiag\unins000.exe /VERYSILENT` |
| Regenerate the reference docs | `.venv\Scripts\python -I scripts\gen_reference.py` |
