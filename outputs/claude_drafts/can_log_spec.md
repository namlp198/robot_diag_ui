# can_log: a firmware ring of every CAN frame (DRAFT, nothing implemented in firmware)

Status: draft for `robot_s_rtos` (H755 CM7, FDCAN1, classic CAN, DMKE motor drivers). Needs its own decision in that repo.

## Why

rdt reads the robot over SWD without stopping it. Today it can sample only the last RX frame (`RxHeader` / `RxData`, one slot) and the
new elements of the 8-element TX FIFO between two polls (`rdt/cantap.py`). A bus running at hundreds of frames per second is
therefore seen only in part, and two identical RX frames in a row cannot be told apart. To see **every** frame, the firmware has to
write each one into a ring that rdt reads in bulk.

## Layout (little-endian, 24 bytes per entry, ring of 256 entries = 6 KiB)

```c
typedef struct {            /* 24 bytes */
    uint32_t seq;           /* running frame number: 0,1,2,... counts RX and TX together, never reset */
    uint32_t tick_us;       /* timestamp: a free-running 1 MHz counter (TIM or DWT/1e6), wraps every ~71 min */
    uint32_t id;            /* 11-bit or 29-bit identifier */
    uint8_t  flags;         /* bit0 TX (0 = RX), bit1 extended id, bit2 RTR, bit3 FD, bit4 BRS */
    uint8_t  dlc;           /* data length in bytes (0..8 classic) */
    uint8_t  pad[2];
    uint8_t  data[8];
} can_log_entry_t;
```

```c
typedef struct {
    uint32_t magic;         /* 'CANL' = 0x4C4E4143 */
    uint32_t version;       /* 1 */
    uint32_t head;          /* next entry to write == total frames logged (not reduced modulo the ring size) */
    uint32_t dropped;       /* frames not logged (should stay 0) */
    can_log_entry_t ring[256];
} can_log_t;
extern can_log_t g_can_log;
```

## Rules

- `can_log_add(...)` is called from the RX callback (`HAL_FDCAN_RxFifo0Callback`, after `HAL_FDCAN_GetRxMessage`) and from one wrapper around
  `HAL_FDCAN_AddMessageToTxFifoQ` so that every frame goes through it. It writes the entry first, then increments `head` (the reader
  trusts `head`).
- rdt polls `head` and the ring; it reconstructs the frames `head_prev .. head-1`. If `head - head_prev > 256` it reports how many were
  overwritten, so loss is explicit. With 256 entries and 1000 frames/s a poll every 100 ms never loses a frame.
- No locking needed for a single writer per direction if `head` is incremented with interrupts masked for the two instructions (an RX
  interrupt and a TX call can interleave).
- The ring is plain SRAM (AXI/D1), so rdt reads it without the "allow peripheral reads" permission.

## rdt side (to write after the firmware exists)

`rdt/can_log.py` decoder and a source in `rdt/cantap.py` that prefers `g_can_log` when the symbol exists; the UI table stays the same.
