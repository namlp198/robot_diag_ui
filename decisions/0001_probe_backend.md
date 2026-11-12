# 0001 Probe backend: pyOCD (read path), CubeProgrammer CLI (flash, later)

- Status: Accepted
- Date: 2026-11-12
- Spike: S1 (`scripts/s1_bench.py`, `scripts/s1_bench_cube.py`)

## Context

`rdt` needs repeated 164-byte SWD reads from two boards at once, read-only (no halt, no reset, no write).
Candidates: pyOCD 0.46.1 and the STM32CubeProgrammer API v2.20.0 (`CubeProgrammer_API.dll` via ctypes).

## Measurement (2026-11-12, 10 s per cell, 164 B per read, 0 failures in every cell)

Both targets were running during all runs. pyOCD: attach mode, 4 MHz, `target_override=cortex_m`.
CubeProgrammer API: HOTPLUG, 4000 kHz. Robot = NUCLEO-H755ZI-Q (ST-LINK V3, CM7, `s_lora_rx` at
0x240005AC). Remote = NUCLEO-F446RE (ST-LINK V2-1, `s_tx` at 0x20000C94: the remote has no `s_lora_rx`,
so a 164 B window of `s_tx` was read).

| Backend | Board | Alone (reads/s) | Both probes at once (reads/s) | p50 / p99 both (ms) |
|---|---|---|---|---|
| pyOCD | robot H755 | 670 | 677 | 1.2 / 2.6 |
| pyOCD | remote F446 | 357 | 419 | 2.3 / 3.3 |
| CubeProgrammer API | robot H755 | 375 | 385 | 2.6 / 6.0 |
| CubeProgrammer API | remote F446 | 318 | 331 | 2.9 / 6.4 |

pyOCD "both" ran as two threads in one process; the Cube API holds one global connection per process, so
"both" there was two processes. The `both` numbers are not lower than `alone`, so the two probes do not
slow each other on this PC (differences are run-to-run noise).

## Decision

Use pyOCD for the read path. It is faster on both boards (1.8x on the H755, 1.1-1.3x on the F446),
runs both probes in one process, and needs no DLL. CubeProgrammer CLI stays the tool for flashing (D5).

## Consequences and caveats

- pyOCD 0.46.1 has no built-in `stm32h755zitx` target and no CMSIS pack is installed, so the session must
  use `target_override=cortex_m`. This works for memory reads. It prints "Invalid coresight component" for ROM
  table entry #5 on the H755 (harmless). Installing the Keil pack (`pyocd pack install`) is not needed for reads.
- H755: pyOCD attached to the CM7 (AP0) while the target ran (core state RUNNING, no halt). That the CM4
  kept running was not checked directly.
- The Cube API needs `setDisplayCallbacks` first and `setLoadersPath(<...>\bin)` before `getStLinkList`;
  without the latter `connectStLink` returns -545 ("Unable to list supported devices").
- Reads/s are for one 164 B block. Several variables need one read per variable, or one read of a
  covering window; the budget per probe is roughly 350-650 block reads/s.
- Only attach was used. Never pass `halt_on_connect`, `connect_mode=under-reset` or a reset to pyOCD.
