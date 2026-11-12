# 00_CONTEXT

## What this is

A diagnostic tool for the robot and its remote over two ST-LINK probes: daemon `rdt` (Python 3.12),
web UI, and an embedded Claude Code chat that sees the same data. Full design and phases:
`plan_chat_ui.md` (draft; section 9 questions are still open).

## State (2026-11-12)

- Done: repo scaffold, `targets.yaml`, `rdt/symbols.py` (spike S2), `rdt resolve`, spike S1 (probe speed,
  decision 0001: pyOCD for reads).
- Not done: S3 Agent SDK, S4 SWO, daemon, UI, chat, recorder, analyzers.
- Verified on hardware (2026-11-12): read-only SWD attach and 164 B reads on both boards while running.
- Not verified: CM4 stays running during CM7 attach; the flashed firmware equals the ELF in the sibling repo.

## S1 numbers (reads/s of 164 B, target running; details in decision 0001)

| Backend | Robot H755 alone / both probes | Remote F446 alone / both probes |
|---|---|---|
| pyOCD 0.46.1 (`target_override=cortex_m`) | 670 / 677 | 357 / 419 |
| CubeProgrammer API 2.20.0 | 375 / 385 | 318 / 331 |

## Facts to keep

- Probes (changed 2026-11-12, user-confirmed): H755 `002900213235510837333439` (ST-LINK V3),
  F446 `066CFF3833584B3043204649` (ST-LINK V2-1). Earlier serials in the plan were `0030004A...` and `0670FF51...`.
- Robot has no usable VCP log (USART3 is shared with the E22 receive path). Robot data comes only
  from SWD variable reads.
- Remote ELF variables (no `rc_state`): `s_rx` (lora_rx_t, 572 B), `s_tx` (lora_tx_t, 184 B), `s_link`
  (robot_link_t, 444 B), `s_robot_link` (448 B), `s_control_out` (116 B), `s_app_input` (40 B). Robot has
  `s_lora_rx` (164 B). Meaning of the fields in each is not yet reviewed.
- Dev machine: Python 3.12.10 installed with winget on 2026-11-12; `py -3.12 -m venv .venv`.
- The two boards do not share a clock; timestamps are taken on the PC.
- Phase order: Spike, D1 core, D2 UI and charts, D3 chat and tools, D4 analyzers and `diag_block_t`,
  D5 scripts and flashing.
