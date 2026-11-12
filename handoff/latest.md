# Latest Handoff

## Date

2026-11-12

## Machine / branch

- Branch: `main`, remote `origin` = `https://github.com/namlp198/robot_diag_ui.git`. Committed locally, not pushed.

## Latest change

- Round 5 (2026-11-12, decision 0009): installable app. `scripts\build_exe.ps1` (UI -> PyInstaller one-folder `dist\RobotDiag\RobotDiag.exe`, 419 MB -> smoke test -> Inno Setup `dist\installer\RobotDiag-Setup-0.2.0.exe`, 180 MB, per-user). Verified on this machine: smoke test (UI, API, Claude SDK bundled, ST-LINK scan), the frozen exe read the real remote (45 reads, firmware matches ELF, 63 RCL frames), its native window opens. User data of the installed app is in `%LOCALAPPDATA%\RobotDiag` (`rdt/paths.py`). **Not done**: running the installer itself (install, uninstall, upgrade), a machine without the repos or Python, code signing (SmartScreen warns). File dialog is now a PowerShell WinForms dialog. Also noted: neither firmware project builds .hex/.bin in CubeIDE (converters off, no post-build); robot_s_rtos produces them via tools/h755-deploy/deploy.bat into outputs/deploy, robot_rc_rtos has nothing.

- Round 4 (2026-11-12, decision 0008): `rdt app` native window (pywebview, default of `start.ps1`); Settings gained Environment (STM32_Programmer_CLI found/Ready, ST-LINK driver scan, Claude login + `claude auth login` button), ELF files per board (add/browse, choose for variables and for image, saved), and firmware files per board (.elf/.hex/.bin, .bin address, saved) that the Flash panel offers; flashing now accepts .hex/.bin. 120 tests pass. **Not verified**: a real flash from a .bin/.hex (the remote is the safe first test), the login button, the tkinter file dialog (needs a person), the native window beyond "it opens and stops the daemon". Install the extra once: `.venv\Scripts\python -m pip install -e .[app]` (already done in this venv).

- CAN frames (2026-11-12, decision 0007): Frames page has a CAN/FDCAN section (`rdt/cantap.py`): last RX frame (`RxHeader`/`RxData`) and new TX FIFO elements of FDCAN1, CANopen-style labels with SDO decode, recorded in sessions (`can_<target>.jsonl`), Claude tool `get_can_frames`. It is sampling, not a bus capture; a full log needs the firmware ring drafted in `outputs/claude_drafts/can_log_spec.md`. Run once read-only on the real robot (223 TX, 83 RX in ~10 s at 20 Hz). Also fixed: `rdt/symbols.py` now resolves `extern`-declared globals (+25 on the robot, +17 on the remote). Restart the daemon (`start.ps1` does it) and enable "allow peripheral reads" in Settings for TX.

- Round 3 (2026-11-12, decision 0006): Timeline findings now translate; known server errors localised; new pages **Gói tin / Frames** (RCL frames decoded from `s_tx.out.frame`, `s_lora_rx.parser.buf`, `s_rx.parser.buf`, `rdt/rcl.py`), **Live Expressions** (variables by name or raw addresses, read-only, `rdt/exprs.py`, `/api/expr`) and **Cài đặt / Settings** (chat model, effort, cost cap, peripheral-read policy; `rdt/settings.py`). Chat header shows readiness, not the model. 99 tests pass; UI checked in headless Edge against a synthetic recorded session. **Not verified on live boards**: that the three frame buffers hold whole frames when polled, how many frames the poll misses at 10 to 20 Hz, Live Expressions values on the real targets, the model/effort settings in a real chat turn (SDK `effort` passes through unchecked).

- UI round (2026-11-12, decision 0005): dark (default) / light hacker-style themes, Vietnamese / English UI (`ui/src/i18n.js`), "Reference" page and `docs/REFERENCE.{en,vi}.md` generated from `rdt/reference.py` (`scripts/gen_reference.py`), "Programmer CLI" page backed by `POST /api/cube/run` (whitelisted read-only commands, HOTPLUG, flash/SRAM reads only; `rdt/cubecli.py`). `scripts/start.ps1` verified by the user. Verified: unit tests, UI in headless Edge (both themes, language switch, reference page, CLI command preview). **Not run**: a real `STM32_Programmer_CLI` call from the Programmer CLI page; the UI with live data after the restyle (charts were only checked empty). Findings are translated to English in the UI by id; the daemon text stays Vietnamese.

- S4 (2026-11-12), read-only part: robot_s_rtos has no ITM output and no SWO config; pyOCD can capture SWO from the ST-LINK; robot ITM/TPIU are off, PB3 is already AF0 (TRACESWO), CPU 200 MHz. `rdt/swo.py` (ITM decoder + line assembler, tested) and `scripts/s4_swo_probe.py` (read-only by default; `--loopback` writes ITM/TPIU debug registers and restores them) are in. **Loopback run once (user approved)**: 0 SWO bytes, registers restored; retry with DBGMCU trace clocks on at 1 Mbaud also 0 bytes; suspect the SWO solder bridge or ST-LINK SWO support. S4 parked. Decision 0004 (open). Hardware tests in `tests/test_backend.py` are opt-in (`RDT_HW_TESTS=1`) because pyOCD's libusb enumeration hung pytest once while CubeIDE was open.

- **Robot flashed (2026-11-12 04:40 UTC, user present, wheels raised, user-approved):** `robot_s_rtos/CM7/SFF02_Release` (the image already on the board): rc 0, "Download verified successfully", flash re-compared with the ELF = match. The robot was off first, which also unpowers its H755 (external supply, no USB power), so the plan failed closed; the user then powered it on and accepted the relaxed gate (wheels off the ground, someone at the robot). After the flash the robot ran again at once: parser frames counting (~20/s), `connected` true, drive_ud 131 (idle), remote link_up true. Both flashes are same-image re-flashes: the path is proven, but no new firmware was deployed. Reset behaviour of PC10/DMKE was not observed on a scope. `sessions/flash_log.jsonl` has both records.

- **First real flash (2026-11-12, user-approved, remote only):** `robot_rc_rtos/SFF_Debug` (the image already on the board) flashed through `/api/flash/run`: CubeProgrammer rc=0, "Download verified successfully", flash re-compared with the ELF = match. Remote ran again right after (control_frames counting from ~2400, link_up true); the robot stayed `connected` and its `lost` rose by the expected restart jump. Bug found by this run and fixed: the daemon's post-flash verification left a probe open (next probe user hung); `read_after` is now a context manager (test added). 

- D5 (2026-11-12): `rdt/sweep.py` (read-only port of link_sweep.ps1: `rdt sweep`, `/api/sweep`, Claude tool `get_sweep`, UI table + CSV; not seen with a real sweep because the remote runs a normal build) and `rdt/flash.py` (gated flashing, decision 0003): `rdt flash-plan` dry run, `/api/flash/plan|run|candidates`, UI card with confirm phrase and motors-safe checkbox. **No board was flashed.** Dry runs on both boards: flashed images give PLAN OK (already flashed), robot_att / ATT images refused. 56 tests pass.
- `targets.yaml` now has `dev_id`, `idcode_addr`, `flash_range`, `allowed_images`, `needs_motors_safe` per target.

- D4 (2026-11-12): `rdt/analyzers.py` rule engine from debug_guide 5.5 and task_history 122/133/147: remote restart, lost jump (not counted as loss), real loss % with bursts, robot not receiving vs remote not sending, CRC, truncated, connected flap, frames-but-not-connected (+LINK_ID hint), remote ESTOP, link_down, tx failures, sample gaps, VCP log patterns. Missing variables skip the rule (listed in `skipped`). Surfaces: `rdt analyze <session>`, `/api/findings`, `/api/sessions/{n}/findings`, live `finding` events every 2 s, UI "Chẩn đoán tự động" panel + timeline, Claude tool `get_findings`. Real 45 s session `d4real`: 1.2% real loss (11 lost / 870), consistent with the chat answer. 38 tests pass.
- `diag_block_t` v1 DRAFT only: `outputs/claude_drafts/diag_block_spec.md` and decoder `rdt/diag_block.py` (+tests). Needs adoption and a decision in robot_s_rtos and robot_rc_rtos; no firmware edited.
- Rules are tuned on one healthy-ish run and synthetic data; thresholds (1.5 s stall, 2 s not-connected, 3 flaps, 200 = restart jump) have not seen a real fault. The VCP regexes are guesses at log wording.

- D3 built (2026-11-12): `rdt/agent_tools.py` (12 read/display tools, unit-tested), `rdt/claude_bridge.py` (Agent SDK 0.2.180, profile "analysis": no built-ins, only `mcp__rdt__*`, settings not loaded), `/api/chat|chat/stop|chat/reset`, UI `Chat.svelte` (messages, tool cards, cost) and `ClaudeCharts.svelte` (show_chart, highlight_range; annotate goes to the timeline). Decision 0002. 22 tests pass.
- **S3 verified live (2026-11-12)**: spike passes (tool call, permission denial, resume); a UI question with both boards running drew a chart and gave a sound answer (`decisions/0002`). The Stop button during a tool call is not tested.

- **RESOLVED (2026-11-12): which firmware is on the boards.** Robot = `robot_s_rtos` model SFF-02 (not `robot_att`); it runs the **SFF02_Release** image (16/16 flash chunks match the Release ELF from 2026-11-11 15:02). Remote = `robot_rc_rtos` **SFF_Debug** (16/16 match). `targets.yaml` now has `image_elf` for the robot: Release has no DWARF, so types come from the SFF02_Debug ELF and addresses from the Release `.symtab` (size mismatch drops the variable). With these, robot `s_lora_rx.parser.stats.frames` 59950 vs remote `s_tx.out.control_frames` 59975: consistent.
- I rebuilt (headless CubeIDE 1.19.0, 0 errors 0 warnings) `robot_rc_rtos` ATT_Debug and `robot_s_rtos` SFF02_Debug in those repos' build folders. Nothing flashed, no source touched.
- `rdt/verify.py` compares 16 flash chunks with the ELF at attach; the daemon shows a banner if they differ. Check it after any re-flash.
- D2 UI (`ui/`, Vite 4 + Svelte 4 + uPlot, Node 17.9): signal path, LoRa link rate charts, flags, timeline (VCP log, flag changes, errors), record button, session replay from the same stores. Built into `ui/dist`, served by the daemon at `http://127.0.0.1:8765/`. Looked at live in the browser pane with both boards. `panels.js` lists the watched variables.

- D1 done: daemon `rdt serve` (`rdt/daemon.py`, FastAPI, loopback only, Host/Origin check): `/api/status|watch|stop|record/start|record/stop|samples|log|symbols|resolve|sessions`, `/ws` live stream. No write endpoint. Verified live on both boards (watch robot+remote+remote VCP, record, stop). 13 tests pass.

- D1: recorder (`rdt record`, `rdt replay`, `sessions/<stamp>/`), sampler, remote VCP log (`--vcp remote`; robot VCP refused in code). Verified on hardware: 6 s record of remote `s_tx` + VCP (18 lines). Older:
- D1 slice: `rdt/backend.py` (read-only pyOCD `Probe`), `rdt watch <target> <paths> [--hz] [--count]` (CSV),
  `tests/test_backend.py` (skips without probe/ELF), `pyocd` as the `probe` extra. Checked on both boards: 5 samples of
  `s_lora_rx.filter.stats.lost` (0, robot) and `s_tx` (remote); check.ps1: 4 passed.

- Spike S1 done: pyOCD vs CubeProgrammer API read rates, decision `decisions/0001_probe_backend.md`
  (pyOCD for reads). Scripts: `scripts/s1_bench.py`, `scripts/s1_bench_cube.py`.
- `targets.yaml`: both probe serials updated (user confirmed the connected pair is the right one).
- Python 3.12.10 installed via winget; `.venv` rebuilt with pyOCD 0.46.1.
- Remote ELF variable names listed in `docs/00_CONTEXT.md`.

## Not done / not verified

- Hardware use was read-only (attach, no halt/reset/write). CM4 still running during CM7 attach was not checked.
- The remote benchmark read `s_tx` (no `s_lora_rx` in that ELF). Field meaning of remote variables not reviewed.
- Flashed firmware vs. sibling-repo ELF not compared.
- `scripts/check.ps1`: OK (4 tests pass).

## Next

Review the signal-path variables against the SFF firmware (`ui/src/panels.js`; robot_s_rtos has its own kinematics/CAN variables), D4 analyzers, D5 scripts and flashing. Open: flash `run` on a bench board (wheels off, power cut) with the user present; paired flashing + RCL_VERSION check; real sweep with the sweep build; D4 threshold tuning on real faults; adopt diag_block_t in firmware.
