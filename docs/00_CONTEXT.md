# 00_CONTEXT

## What this is

A diagnostic tool for the robot and its remote over two ST-LINK probes: daemon `rdt` (Python 3.12),
web UI, and an embedded Claude Code chat that sees the same data. Full design and phases:
`plan_chat_ui.md` (draft; section 9 questions are still open).

## State (2026-11-11)

- Done: repo scaffold, `targets.yaml`, `rdt/symbols.py` (spike S2: variable path to address from
  DWARF, verified against the robot_att CM7 ELF), `rdt resolve`.
- Not done: S1 probe speed (no ST-LINK was detected on 2026-11-11, robot and remote were off), S3
  Agent SDK, S4 SWO, daemon, UI, chat, recorder, analyzers.
- Not verified: any real SWD read; remote-side variable names (`rc_state` is not in the ELF).

## Facts to keep

- Probes: H755 `0030004A3235510837333439`, F446 `0670FF514988525067182431`.
- Robot has no usable VCP log (USART3 is shared with the E22 receive path). Robot data comes only
  from SWD variable reads.
- The two boards do not share a clock; timestamps are taken on the PC.
- Phase order: Spike, D1 core, D2 UI and charts, D3 chat and tools, D4 analyzers and `diag_block_t`,
  D5 scripts and flashing.
