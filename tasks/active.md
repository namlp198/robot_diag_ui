# Active Task

## Current Task

Spike S1: measure SWD read rate on both boards.

## Goal

Choose the probe backend (pyOCD or CubeProgrammer API) by measured reads per second on F446 and
H755, with both probes attached at once and the target running.

## Steps

1. Power the robot and the remote; `pyocd list` and `STM32_Programmer_CLI -l st` must show both serials.
2. Attach read-only (no halt, no reset). Read `s_lora_rx` (164 B) in a loop for 10 s per probe, then
   both probes together; record reads/s and failures.
3. H755: confirm pyOCD can attach to CM7 while CM4 runs; if not, use the CubeProgrammer API.
4. Write the numbers into `docs/00_CONTEXT.md` and a decision record 0001.
5. Look up the remote's blackboard variable names in the ELF (`rc_state` does not exist).

## Done when

Four numbers (2 backends x 2 boards) and a backend choice are recorded.
