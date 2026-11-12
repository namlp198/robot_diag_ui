# robot_diag_ui

Diagnostic tool for the robot (`robot_s_rtos` SFF-02 on an H755) and its remote (`robot_rc_rtos`, F446), read over
two ST-LINK probes. A local daemon (`rdt`) owns the hardware; a web UI shows live data and
charts; a Claude Code chat panel looks at the same data and can draw on the charts.

Status (2026-11-12): daemon, web UI, recorder, Claude chat, analyzers, sweep and gated flashing are built (decisions 0001-0003). Spike S4 (SWO) is not run. `handoff/latest.md` says what is verified on hardware.

## Layout

| Path | Content |
|---|---|
| `rdt/` | Python package: symbols (DWARF), CLI; later targets, backends, recorder, analyzers, claude bridge |
| `ui/` | Web UI (Vite + Svelte + uPlot), planned for D2 |
| `targets.yaml` | Probe serials, ELF paths, log ports |
| `tests/` | pytest; tests needing an ELF or a probe skip when it is absent |
| `docs/` | `00_CONTEXT.md`, `README_AI_WORKFLOW.md`, `plan_chat_ui.md` |
| `decisions/` | Decision records (index in `0000_INDEX.md`) |
| `tasks/`, `handoff/` | Active work and the session handoff |
| `scripts/` | `check.ps1`, `toolchain.psd1` |
| `sessions/` | Recorded measurement sessions (git-ignored) |
| `outputs/` | Drafts, reviews, debug reports, temporary files |

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.\scripts\check.ps1
```

## Use

```powershell
.venv\Scripts\rdt resolve robot s_lora_rx.filter.stats.lost
```

`targets.yaml` paths to ELF files are relative to this repo and point at the sibling repos
(`../robot_att`, `../robot_rc_rtos`).

## Safety

Read-only first: no halt, no reset, no memory write while a robot can run its motors. Never open the
robot's USART3 VCP (shared with the E22 receive path). Details: plan section 6.
