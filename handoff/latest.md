# Latest Handoff

## Date

2026-11-12

## Machine / branch

- Branch: `main`, remote `origin` = `https://github.com/namlp198/robot_diag_ui.git`. Committed locally, not pushed.

## Latest change

- **FINDING (2026-11-12): neither board runs the firmware the sibling-repo ELFs were built from.** `rdt/verify.py` compares 16 flash chunks with the ELF: robot 16/16 differ (vector table differs; `s_lora_rx.control_frames` reads 115200, a UART baud, so the layout differs too), remote 15/16 differ (vector table shifted by 0x10, counters still plausible vs its VCP log). Robot-side values are NOT trustworthy until the matching ELF is found/rebuilt. The daemon runs the check on attach and the UI shows a red banner.
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

Get ELFs that match the flashed firmware (or rebuild + flash with the user's OK), then re-check the UI panels. Then D3 chat (needs spike S3), D4 analyzers.
