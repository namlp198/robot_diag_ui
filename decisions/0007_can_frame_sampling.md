# 0007: CAN / FDCAN frame sampling on the robot

- Status: Accepted as best effort; run once on the real robot (read-only, 20 Hz poll, about 10 s: 223 TX and 83 RX frames sampled, 10 possible TX overwrites); complete capture needs a firmware ring (draft only)
- Date: 2026-11-12

## Decision

- `rdt/cantap.py` (polled by the robot's sampler every tick, read-only) shows: the last RX frame (`RxHeader` + `RxData`, SRAM) and the new
  elements of the FDCAN1 TX FIFO (message RAM at `hfdcan1.msgRam.TxFIFOQSA`, put index from the TXFQS register at `hfdcan1.Instance + 0xC4`).
  Addresses and sizes come from the ELF and from the handle in target memory, none hard-coded except the TXFQS register offset (from `stm32h755xx.h`).
  Frames get a CANopen-style label (the DMKE drivers answer 0x58x to requests on 0x60x) with SDO read/write/abort decoded.
- The TX tap reads peripheral-range addresses, so it follows the "allow peripheral reads" setting; without it only RX is sampled and the UI says so.
- PSR (reading resets the last-error code) and ECR (CEL is cleared on read) are never read by rdt on purpose; the reference docs say why.
- Sampled frames appear in Frames > CAN, are recorded in sessions (`can_<target>.jsonl`), and Claude can read them (`get_can_frames`).
- "Every frame" is not possible over SWD polling: the RX slot holds one frame, the TX FIFO eight. The tap counts "possible overwrites" when the
  number of new TX elements reaches the FIFO size minus one. A complete log needs a ring of every frame in `robot_s_rtos`: draft in
  `outputs/claude_drafts/can_log_spec.md` (needs its own decision there).

## Also fixed here

`rdt/symbols.py` ignored variables declared `extern` in a header (their definition DIE has `DW_AT_specification` and no name or type of its
own). They resolve now: 25 more variables on the robot (including `RxData`) and 17 more on the remote.

## Seen on the real robot (first run)

- TX: SDO read requests on 0x601 and 0x602 (objects such as 0x2201, 0x2183, 0x6069, 0x221C). RX: SDO responses on 0x581 and 0x582 (for example 0x2201 = 504, 0x6069 = 0) and a periodic 29-bit frame 0x18EFFF80 (3 bytes, J1939-style, source address 0x80) that is not from the DMKE drivers' SDO traffic; who sends it is not known.
- The HAL in `robot_s_rtos` stores `RxHeader.DataLength` as the plain DLC code (0..15), not shifted by 16; the first version of the decoder assumed the shift and dropped every RX frame until it was compared with a real header.

## Open

How many frames the poll misses against the real traffic (the tap only counts "possible overwrites", it cannot count what it never saw), and the FDCAN bit rate
(from the source, not measured). FDCAN2/3 and the CM4 are not covered.
