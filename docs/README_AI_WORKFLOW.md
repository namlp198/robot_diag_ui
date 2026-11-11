# README_AI_WORKFLOW

## Repository identity

- Repository: `robot_diag_ui` (GitHub `namlp198/robot_diag_ui`)
- Created: 2026-11-11, branch `main`
- Sibling repos it reads: `robot_att` (robot, H755 CM7), `robot_rc_rtos` (remote, F446),
  `robot_link` (RCL v1 spec and `python/rcl.py`)

## Read before changing code

1. `README.md`
2. `docs/00_CONTEXT.md`
3. `tasks/active.md`
4. `handoff/latest.md`
5. `decisions/0000_INDEX.md`

## Workflow

- Read only the files needed for the current task; keep changes small and reviewable.
- Update `tasks/active.md` when the task changes and `handoff/latest.md` before ending a session.
- Update `docs/00_CONTEXT.md` when project state materially changes.
- Architecture choices (backend, UI stack, chat embedding, `diag_block_t`) get a record in `decisions/`.
- Firmware-side changes (for example `diag_block_t`) are made in the firmware repo with its own
  decision there, not from here.
