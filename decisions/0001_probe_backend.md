# 0001 Probe backend

Status: Pending (needs spike S1 numbers)

## Context

Reads must reach ~20-50 Hz per board while the target runs, with two probes at once. pyOCD is fast
in exclusive mode but H755 support is unchecked; the CubeProgrammer API is supported by ST but is
heavier to embed. `STM32_Programmer_CLI` per read (~1/s) is the current manual method.

## Decision

None yet. Record measured reads/s per backend per board here, then choose.
