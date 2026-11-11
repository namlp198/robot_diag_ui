# Latest Handoff

## Date

2026-11-11

## Machine / branch

- Branch: `main`, remote `origin` = `https://github.com/namlp198/robot_diag_ui.git`.

## Latest change

- Repo scaffold modeled on robot_att / robot_link: README, CLAUDE.md, AGENTS.md, docs, tasks,
  decisions, handoff, scripts, outputs.
- `rdt/symbols.py` and `rdt resolve` (S2) work; 3 tests pass against the robot_att CM7 ELF.
- Plan moved to `docs/plan_chat_ui.md`.

## Not done / not verified

- S1 did not run: pyOCD and STM32_Programmer_CLI saw no ST-LINK (robot and remote were off).
- No hardware read has been made. Remote-side variable names are unknown (`rc_state` absent).

## Next

Power both boards, run S1 per `tasks/active.md`.
