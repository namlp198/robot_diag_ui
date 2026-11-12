# Latest Handoff

## Date

2026-11-12

## Machine / branch

- Branch: `main`, remote `origin` = `https://github.com/namlp198/robot_diag_ui.git`. Committed locally, not pushed.

## Latest change

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

Review the signal-path variables against the SFF firmware (`ui/src/panels.js`; robot_s_rtos has its own kinematics/CAN variables), then D3 chat (spike S3 first), D4 analyzers.
