# rdt reference: monitored data and command lists

Generated from `rdt/reference.py` by `scripts/gen_reference.py`. Do not edit by hand.

## Monitored data

Variables read over SWD without stopping the cores. Names are resolved from the flashed ELF (never hard-coded offsets).

| Variable | Board | Shown in | Meaning |
|---|---|---|---|
| `s_app_input.data.controls.drive_ud` | remote | signal | Drive up/down stick value the remote application reads from the operator. |
| `s_app_input.data.alive_tick` | remote | signal | Counter the input task increments each cycle; stops when the input task hangs. |
| `s_tx.out.source` | remote | signal | Which input source the arbiter selected for the frame being sent. |
| `s_tx.arbiter.armed` | remote | signal,flags | Arbiter armed state: the remote is allowed to send drive commands. |
| `s_tx.out.sent.drive_ud` | remote | signal | drive_ud value inside the last CONTROL frame the remote sent. |
| `s_tx.out.control_frames` | remote | signal,link | Count of CONTROL frames sent. A drop means the remote restarted. |
| `s_tx.out.tx_failures` | remote | link | Count of failed sends to the radio module (E22) or UART. |
| `s_tx.out.input_valid` | remote | flags | True when the remote has a valid operator input to send. |
| `s_tx.out.sent.estop` | remote | flags | ESTOP flag in the last CONTROL frame; set means the remote is asking the robot to stop. |
| `s_tx.out.sweep_step` | remote | sweep | Current step of the Phase 0 sweep build (send-rate test). |
| `s_tx.out.sweep_gap_ms` | remote | sweep | Gap between frames (ms) at the current sweep step. |
| `s_link.link_up` | remote | flags | Remote's own view that the link to the robot is up (telemetry received). Meaningful on SFF/MFF builds. |
| `s_link.frames_ok` | remote | link | Telemetry frames from the robot received correctly. |
| `s_link.frames_bad` | remote | link | Telemetry frames from the robot received corrupted. |
| `s_link.frames_lost` | remote | link | Telemetry frames from the robot detected as missing (sequence gaps). |
| `s_tx.out.frame` | remote | frames | The last RCL frame the remote built for sending (58-byte buffer; `frame_len` says how many bytes are the frame). |
| `s_tx.out.frame_len` | remote | frames | Length in bytes of the frame in `s_tx.out.frame`. |
| `s_rx.parser.buf` | remote | frames | Byte buffer of the remote's receive parser; holds the last telemetry frame from the robot until the next one overwrites it. |
| `s_lora_rx.parser.buf` | robot | frames | Byte buffer of the robot's receive parser; holds the last CONTROL frame from the remote until the next one overwrites it. |
| `RxHeader` | robot | can | HAL header (identifier, ID type, length, timestamp) of the last CAN frame the firmware took out of RX FIFO0. One slot, overwritten by every frame. |
| `RxData` | robot | can | The 8 data bytes of the same last received CAN frame. |
| `hfdcan1.Instance` | robot | can | Pointer to the FDCAN1 registers; rdt reads the TXFQS register (offset 0xC4: TX FIFO put index and free level) to see how many frames were queued since the last poll. Needs 'allow peripheral reads'. PSR and ECR are deliberately not read: reading them changes what the firmware sees. |
| `hfdcan1.msgRam.TxFIFOQSA` | robot | can | Start address of the TX FIFO in the FDCAN message RAM; its elements (identifier, length, data) are read to rebuild the frames queued for sending. With TxElmtSize and TxFifoQueueElmtsNbr (element size in words, number of elements). |
| `s_lora_rx.parser.stats.frames` | robot | signal,link | Frames the robot's LoRa parser decoded. |
| `s_lora_rx.parser.stats.crc_errors` | robot | link | Frames dropped for a bad CRC (noise, wrong baud, remote not speaking RCL v1). |
| `s_lora_rx.parser.stats.truncated` | robot | link | Frames cut short (remote sending slower than 500 ms or weak signal). |
| `s_lora_rx.filter.stats.accepted` | robot | signal,sweep | Frames the filter accepted (right link ID, in sequence). |
| `s_lora_rx.filter.stats.lost` | robot | link | Frames missing by sequence number. A jump of 200 or more is a remote restart, not real loss. |
| `s_lora_rx.filter.stats.duplicates` | robot | link | Frames repeating an already seen sequence number. |
| `s_lora_rx.filter.stats.err_link_id` | robot | analyzers | Frames rejected because their LINK_ID differs from the one the robot locked. |
| `s_lora_rx.input.drive_ud` | robot | signal | drive_ud the robot's input stage holds after the filter. |
| `s_lora_rx.control_frames` | robot | signal | Count of CONTROL frames delivered to the robot's input stage. |
| `s_lora_rx.connected` | robot | flags,analyzers | Robot considers the remote connected (fresh valid frames). |
| `s_lora_rx.input.connected` | robot | flags | Connected flag as seen at the robot's input stage. |
| `s_lora_rx.input.button_emergency` | robot | flags | Emergency stop requested; set is a problem state. |

## Automatic diagnosis rules

Findings state evidence and what to check next; they do not claim a cause as fact.

| Rule | Severity | Meaning |
|---|---|---|
| `remote_restart` | warn | Remote's control_frames dropped: it reset (sequence back to 0). |
| `lost_jump` | info | One step of `lost` of 200+: a remote restart, excluded from the loss rate. |
| `link_loss` | info/warn/error | Real loss percentage from `lost` against frames received (under 1 % info, under 5 % warn). |
| `robot_not_receiving` | error | Remote keeps sending but the robot's parser frames stand still. |
| `remote_not_sending` | warn | Neither the remote's counter nor the robot's frames move. |
| `crc_errors` | warn | CRC errors counted by the robot. |
| `truncated` | info | Truncated frames at the robot. |
| `remote_tx_failures` | warn | Remote failed to send. |
| `remote_rx_bad` | info | Remote received corrupted telemetry. |
| `connected_flap` | warn | `connected` toggles repeatedly. |
| `frames_not_connected` | error | Frames arrive but `connected` stays false (often a different LINK_ID was locked). |
| `remote_estop` | info | Remote is sending the ESTOP flag. |
| `remote_link_down` | warn | Remote reports link_up = false. |
| `sample_gap` | info | A gap in samples (SWD read delayed): data around it needs care. |
| `log_watchdog / log_fault / log_stack` | warn | A remote VCP log line mentions watchdog, a fault or a stack problem (quoted as data). |

## pyOCD functions rdt uses

Python API (pyOCD 0.46.1).

| Command | Syntax | Safety | Meaning | rdt uses it |
|---|---|---|---|---|
| `ConnectHelper.session_with_chosen_probe` | `session_with_chosen_probe(unique_id=<serial>, connect_mode='attach', halt_on_connect=False, resume_on_disconnect=False, options={'frequency': 4000000, 'target_override': 'cortex_m'})` | read-only | Opens a debug session to one probe by serial. rdt uses attach mode (no halt, no reset) and the generic cortex_m target because pyOCD has no H755 pack. | yes |
| `session.open() / close()` | `session.open(); session.close()` | read-only | Starts and releases the SWD connection. Releasing matters: an unclosed session blocks the next user of the probe. | yes |
| `target.read_memory_block8` | `target.read_memory_block8(address, size) -> list[int]` | read-only | Reads `size` bytes from target memory without stopping the core. This is how every monitored variable is sampled. | yes |
| `target.read32` | `target.read32(address) -> int` | read-only | Reads one 32-bit word (used by the spike scripts for debug registers). | no |
| `DebugProbeAggregator.get_all_connected_probes` | `get_all_connected_probes(unique_id=None)` | read-only | Lists attached probes; rdt matches the serials from targets.yaml. | yes |
| `target.write32 / write8` | `target.write32(address, value)` | writes the target | Writes target memory or registers. Not used by the daemon; only spike S4's opt-in loopback wrote ITM/TPIU debug registers (restored afterwards). | no |
| `probe.swo_start / swo_read / swo_stop` | `probe.swo_start(baud); probe.swo_read(); probe.swo_stop()` | read-only | Captures SWO trace bytes through the ST-LINK. Spike S4 only; on the robot it returned no bytes (decision 0004). | no |

## pyOCD command line

For manual debugging; stop rdt first because one probe serves one session. rdt itself only reads.

| Command | Syntax | Safety | Meaning | rdt uses it |
|---|---|---|---|---|
| `pyocd list` | `pyocd list [--targets] [--probes]` | read-only | Lists connected probes (with their unique IDs) or the supported targets. | no |
| `pyocd commander` | `pyocd commander -u <serial> -t cortex_m --connect attach [-c "<cmd>"]` | read-only | Interactive or one-shot debug shell (alias `pyocd cmd`). `-u` selects the probe, `-t` the target type, `--connect attach` avoids halting the core. | no |
| `commander: status` | `status` | read-only | Shows whether the core is running or halted. | no |
| `commander: read32 / read8` | `read32 <addr> [<count>]` | read-only | Reads 32-bit (or 8-bit) words from memory; the same access as rdt's sampling. | no |
| `commander: reg` | `reg [<name>]` | read-only | Shows core registers. Reads registers, so on a running core the values are a snapshot that may need a halt. | no |
| `commander: show map` | `show map` | read-only | Shows the target memory map pyOCD uses. | no |
| `commander: halt / go / step / reset` | `halt \| go \| step \| reset [halt]` | controls the core (halt/reset/run) | Stops the core, resumes it, single-steps, or resets. On a robot with live motors these are unsafe; rdt never issues them. | no |
| `commander: write32 / write8` | `write32 <addr> <value>` | writes the target | Writes memory or registers. rdt's rule: never write target memory. | no |
| `pyocd flash / load` | `pyocd flash -t <target> <file.elf\|hex\|bin>` | writes the target | Programs flash with pyOCD. rdt flashes with STM32_Programmer_CLI instead (gated Flash panel). | no |
| `pyocd gdbserver` | `pyocd gdbserver -u <serial>` | controls the core (halt/reset/run) | Starts a GDB server on the probe (holds the probe exclusively; stop rdt first). | no |

## STM32_Programmer_CLI

STM32CubeProgrammer command line (2.20.0). The Programmer CLI page runs only the read commands; flashing is in the gated Flash panel.

| Command | Syntax | Safety | Meaning | rdt uses it |
|---|---|---|---|---|
| `-l st-link` | `STM32_Programmer_CLI -l st-link` | read-only | Lists ST-LINK probes with serial numbers and firmware versions. UI: Programmer CLI > List probes. | yes |
| `-c port=SWD` | `-c port=SWD sn=<serial> mode=HOTPLUG [freq=<kHz>] [ap=<n>] [reset=<SWrst\|HWrst\|Crst>]` | read-only | Connects to the target over SWD. `sn` picks the probe. `mode`: HOTPLUG attaches to the running target without halting or resetting (rdt's reads); NORMAL (default) connects and may halt or reset the core (used for flashing); UR connects under reset. `ap` picks the access port (core). | yes |
| `-r32` | `-r32 <addr> <size>` | read-only | Reads `size` bytes starting at `addr` and prints 32-bit words. rdt limits it to flash and SRAM, 4-byte aligned, at most 4 KiB. | yes |
| `-ob displ` | `-ob displ` | read-only | Displays the option bytes (read protection level, boot addresses, watchdog and bank settings). | yes |
| `-w` | `-w <file.elf\|hex\|bin> [<addr>]` | writes the target | Programs the file into flash (alias `-d`). .bin needs an address. rdt uses it only in the gated Flash panel, with .elf images. | yes |
| `-v` | `-v` | read-only | Verifies flash content against the file after programming. | yes |
| `-rst` | `-rst` | controls the core (halt/reset/run) | Resets the core after the other commands finish. rdt adds it to the flash command so the new firmware starts. | yes |
| `-hardRst` | `-hardRst` | controls the core (halt/reset/run) | Hardware reset through the NRST line. Not used by rdt. | no |
| `-halt / -run` | `-halt \| -run` | controls the core (halt/reset/run) | Halts the core / starts execution. Not used by rdt (read-only policy). | no |
| `-e` | `-e all \| -e <sector,...>` | dangerous (erase / protection) | Erases the whole flash or the listed sectors. Not exposed by rdt; flashing erases only what the programmed segments need. | no |
| `-ob <option>=<value>` | `-ob RDP=0xAA \| -ob BOR_LEV=...` | dangerous (erase / protection) | Writes option bytes. Setting RDP back to level 0 mass-erases the flash. Never run from rdt. | no |
| `-vb / -log` | `-vb <1\|2\|3> \| -log <file>` | read-only | Verbosity of the output / writes the output to a log file. | no |
