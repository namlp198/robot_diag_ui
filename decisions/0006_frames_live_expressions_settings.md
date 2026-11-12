# 0006: RCL frame view, Live Expressions, chat settings

- Status: Accepted (verified with unit tests and a synthetic session in headless Edge; **not yet run against live boards**)
- Date: 2026-11-12

## Decision

- **Frames** (`rdt/rcl.py`, `Frames.svelte`): the daemon samples three buffers the firmware already keeps, with the other watched variables: the remote's last sent frame (`s_tx.out.frame`, `frame_len`), the robot's parser buffer (`s_lora_rx.parser.buf`) and the remote's parser buffer (`s_rx.parser.buf`). A frame is reported only when it passes the CRC (a read can catch a buffer being rewritten) and differs from the previous one of that source. It is decoded per RCL v1 (header fields, CONTROL flags/axes/slots/TLV, TELEMETRY flags/records, INFO) and shown with a coloured hex dump, a history table and a SEQ comparison of what the remote sent against what the robot received. Capture is by polling, not a line capture: frames can be missed when the poll rate is below the send rate; the UI says so. The robot has no buffer for the telemetry it sends, so robot → remote is visible only on the remote's receive side. Frames of a recorded session are rebuilt from the buffer columns in its CSV. Claude has `get_frames` (read-only).
- **Live Expressions** (`rdt/exprs.py`, `LiveExpr.svelte`): watch a variable by name (ELF) or a raw address with a type and count, read-only, on every sampling tick of the running sampler (no second probe session). The list lives in the browser (localStorage) and is sent to the daemon. Regions: flash, SRAM and the Cortex-M core registers (0xE000_0000..0xE00F_FFFF) always; peripheral registers (0x4000_0000..0x5FFF_FFFF) only when "allow peripheral reads" is on in Settings (default off), because reading a status/data register can clear a flag or pop a FIFO byte; anything else is refused. Nothing writes.
- **Settings** (`rdt/settings.py`, `Settings.svelte`, `sessions/settings.json`): chat model, effort (SDK `effort`) and cost cap, the peripheral-read policy, theme and language. Changes apply from the next conversation (the daemon starts a new one when the chat is idle). The chat header no longer shows the model: it shows whether the chat is usable (`claude auth status` of the bundled CLI, cached 30 s). There is no engine choice: the Claude Agent SDK is the only engine.
- UI text: finding events in the Timeline are re-translated from the finding id; known server errors and flash check names are localised (`localizeError`).

## Consequences

- `ui/src/panels.js` `FRAME_BUFFERS` adds three buffer reads per tick (58 bytes each); `rdt/reference.py` documents them.
- Bytes variables in a session CSV pass through a number parser: a hex string made only of digits (or like `12e4`) turns into a number. Frame buffers start with `A5 C3`, so frames are safe; other bytes columns are not (known, not fixed).
- Svelte: a `$:` block that assigns something it reads loops forever (found twice); use store subscriptions for such updates.
