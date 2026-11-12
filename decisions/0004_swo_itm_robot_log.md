# 0004 SWO/ITM as a robot log source (spike S4)

- Status: Open. Read-only part done 2026-11-12; the capture chain is **not verified** (first loopback on 2026-11-12 received no bytes; see "Loopback result").
- Date: 2026-11-12

## Question

The robot has no usable VCP log (USART3 is shared with the E22 receive path). Can SWO/ITM through the ST-LINK V3 replace it?

## Findings (read-only)

- Firmware `robot_s_rtos` (CM7) emits nothing on ITM: no `ITM_SendChar`, `__io_putchar` is declared weak and never defined (`syscalls.c`), and the `.ioc` has no SWO/trace
  configuration. So today there is no data to capture, whatever the probe can do. Any use needs a firmware change in `robot_s_rtos` (its own decision there).
- Host side: pyOCD 0.46.1 can capture SWO from an ST-LINK (`StlinkProbe.swo_start/swo_read`, `SWV_START_TRACE_RECEPTION`). `rdt/swo.py` decodes ITM packets and
  assembles text lines with the same cleaning as VCP text (tested offline, `tests/test_swo.py`). CubeProgrammer CLI has no SWO capture.
- Robot MCU state now: CPU is Cortex-M7 at 200 MHz (`.ioc` SYSCLK), DEMCR.TRCENA = 1, ITM disabled (TCR = 0, TER = 0), TPIU ACPR/SPPR/FFCR = 0, DBGMCU_CR = 0. PB3 is in
  alternate function 0 (TRACESWO), i.e. the pin is already routed to SWO at reset.
- The remote (F446) has a working VCP, so it does not need this.

## Not verified

Whether the Nucleo's SWO solder bridge connects PB3 to the ST-LINK on this board, and whether the ST-LINK V3 delivers bytes. `scripts/s4_swo_probe.py --loopback` tests exactly
that without firmware: it enables ITM/TPIU (debug registers, volatile, restored afterwards), writes a test string to stimulus port 0 from the debugger, and reads it back over SWO.

## Loopback result (2026-11-12, robot powered, wheels raised, user approved the register writes)

`--loopback` ran with 200 MHz / 2 Mbaud (ACPR 99): **0 SWO bytes received**; all written registers were restored (state after equals state before).
So the chain is not confirmed. Untested likely causes: `DBGMCU_CR` trace clock enables (TRACECLKEN, D1/D3 debug clocks) were left at 0 and the loopback does not set them;
the SWO solder bridge (PB3 to ST-LINK) may be open; the ST-LINK SWO speed may not match 2 Mbaud. A retry that also writes `DBGMCU_CR` (volatile) and tries 1 Mbaud
needs a new user approval. SWO is not needed for the current plan.

## Decision so far

Keep named-variable reads (and later `diag_block_t`) as the robot data source. SWO is worth adopting only if the loopback works AND `robot_s_rtos` adopts an ITM log
(`__io_putchar` -> `ITM_SendChar`, with TPIU configured by firmware or by rdt on attach). Until then no code in the daemon depends on it.
