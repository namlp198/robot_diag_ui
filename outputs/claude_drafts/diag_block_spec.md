# diag_block_t v1: draft spec (2026-11-12)

Status: **draft, from robot_diag_ui. No firmware has it.** Each firmware repo (`robot_s_rtos`, `robot_rc_rtos`) adopts it with its
own decision record, C header and tests; the Python decoder is `rdt/diag_block.py` (tested against `encode()` there, which is the
reference for the byte layout). This repo does not edit firmware.

## Why

Today robot_diag reads about 25 internal variables by name. A renamed variable silently breaks a panel and each read costs one SWD
transaction. One 108-byte block read gives a consistent snapshot, survives refactors, and carries `product`, firmware version and reset cause.

## Layout (little endian, packed, 108 bytes)

```c
typedef struct __attribute__((packed)) {
    uint32_t magic;          /* 0x47414944, bytes 44 49 41 47 ("DIAG") */
    uint16_t version;        /* 1 */
    uint16_t size;           /* sizeof(diag_block_t) = 108 */
    uint8_t  product;        /* 1 SFF remote, 2 MFF remote, 3 ATT remote, 11 robot SFF-01, 12 robot SFF-02, 13 robot ATT */
    uint8_t  fw[3];          /* major, minor, patch */
    uint32_t seq;            /* seqlock: odd while the block is being written, even when stable; +2 per update */
    uint32_t uptime_ms;
    uint32_t reset_cause;    /* RCC reset flags captured at boot, before clearing */
    uint32_t reset_count;    /* since power-on (retained or backup SRAM; 0 if not retained) */
    uint32_t rx_bytes, frames_ok, crc_err, truncated, lost, dup, err_link_id, tx_frames, tx_fail;
    uint32_t last_rx_age_ms; /* now - last accepted frame; 0xFFFFFFFF if none yet */
    uint16_t flags;          /* bit0 connected, 1 failsafe, 2 estop, 3 armed, 4 input_valid, 5 can_bus_off */
    uint8_t  link_quality;   /* 0..100, remote only; 0xFF unknown */
    uint8_t  pad;
    uint32_t heap_free, heap_min;
    uint16_t stack_min_words[8]; /* high-water mark of the first 8 tasks in the supervisor's order; 0xFFFF unused */
    uint32_t fdcan_psr, fdcan_ecr; /* raw registers (robot); 0 on the remote */
    uint32_t crc32;          /* zlib CRC-32 of the 104 bytes above */
} diag_block_t;
_Static_assert(sizeof(diag_block_t) == 108, "diag_block_t layout");
```

## Rules

- One global, `diag_block_t g_diag;`, found by the tool through the ELF symbol name `g_diag` (never a hard-coded address).
- Writer: `seq++` (odd), fill fields, compute crc32, `seq++` (even). A single writer task; no mutex is needed for readers.
- Reader (rdt): read, decode, read again; accept if both are valid and `seq` is equal (`read_consistent`).
- Counters are monotonic u32; the tool computes rates. `lost` keeps the firmware's definition (SEQ gap, so a remote restart adds ~255).
- Adding fields means a new `version`; the decoder refuses unknown versions instead of guessing.

## What the firmware owners decide

Where `g_diag` lives (SRAM that is not cleared on reset for `reset_count`), who writes it, update period (10 Hz is enough), the
`product` numbering, and whether `fdcan_*` and `stack_min_words` are filled in the first version. Until then rdt keeps reading named variables.
