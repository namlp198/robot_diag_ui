# robot_diag_ui

Diagnostic tool for the robot (`robot_s_rtos` SFF-02 on an H755) and its remote (`robot_rc_rtos`, F446), read over
two ST-LINK probes. A local daemon (`rdt`) owns the hardware; a web UI shows live data and
charts; a Claude Code chat panel looks at the same data and can draw on the charts.

Status (2026-11-12): spikes S1-S3 and stages D1-D5 are built: daemon, web UI, recorder/replay, Claude chat, analyzers,
sweep and gated flashing (decisions 0001-0003). Spike S4 (SWO on the H755) is parked: two loopback runs got no SWO bytes
(decision 0004). `handoff/latest.md` says what is verified on hardware and what is still open.

## Layout

| Path | Content |
|---|---|
| `rdt/` | Python package: symbols (DWARF), probe backend, sampler, recorder, VCP log, daemon (FastAPI), Claude bridge and tools, analyzers, sweep, gated flash, CLI |
| `ui/` | Web UI (Vite + Svelte + uPlot); the built UI in `ui/dist` is served by the daemon |
| `targets.yaml` | Probe serials, ELF paths (Debug for symbols, Release for the flashed image), log ports, flash gates |
| `tests/` | pytest; tests needing an ELF or a probe skip when it is absent (probe tests: `RDT_HW_TESTS=1`) |
| `docs/` | `00_CONTEXT.md`, `README_AI_WORKFLOW.md`, `plan_chat_ui.md` |
| `decisions/` | Decision records (index in `0000_INDEX.md`) |
| `tasks/`, `handoff/` | Active work and the session handoff |
| `scripts/` | `start.ps1`, `make_shortcut.ps1`, `check.ps1`, `toolchain.psd1`, spike scripts `s*_*.py` |
| `sessions/` | Recorded measurement sessions and `flash_log.jsonl` (git-ignored) |
| `outputs/` | Drafts, reviews, debug reports, temporary files |

## Setup

Needs Python 3.12, Node (only to rebuild the UI), the two ST-LINK probes, and for flashing STM32CubeProgrammer
(path pinned in `scripts/toolchain.psd1`). The chat needs a one-time login of the bundled Claude CLI.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
cd ui; npm install; npm run build; cd ..     # builds ui/dist
.\scripts\check.ps1
```

## Run

```powershell
.\scripts\start.ps1              # daemon + UI in its own Edge app window; closing the window stops the daemon
.\scripts\start.ps1 -Browser     # same, but opens the default browser; stop with Ctrl+C
.\scripts\make_shortcut.ps1      # puts a "Robot Diag" shortcut on the desktop
.venv\Scripts\rdt serve          # daemon only, UI at http://127.0.0.1:8765
```

The daemon listens on 127.0.0.1 only and owns the probes: close CubeIDE/CubeProgrammer sessions on the same probes and
run one daemon at a time. Other commands: `rdt watch|record|replay|analyze|sweep|flash-plan|resolve` (see `rdt --help`).
The UI has a dark (default) and a light theme and Vietnamese/English (buttons top right; remembered in the browser).
Pages: Dashboard, Programmer CLI (read-only `STM32_Programmer_CLI` commands) and Reference (monitored variables, rules,
pyOCD and `STM32_Programmer_CLI` commands with their meaning; the same text is in `docs/REFERENCE.en.md` and
`docs/REFERENCE.vi.md`, regenerated with `python -I scripts/gen_reference.py` after editing `rdt/reference.py`).
Optional env: `RDT_CHAT_MODEL`, `RDT_CHAT_MAX_USD` (chat cost cap, default 2.0).

`targets.yaml` paths to ELF files are relative to this repo and point at the sibling repos
(`../robot_s_rtos`, `../robot_rc_rtos`).

## Safety

Read-only first: no halt, no reset, no memory write while a robot can run its motors. Never open the
robot's USART3 VCP (shared with the E22 receive path). Details: plan section 6.
