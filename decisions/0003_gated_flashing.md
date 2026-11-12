# 0003 Gated flashing and read-only sweep

- Status: Accepted; `run` verified on both boards on 2026-11-12 with same-image re-flashes (remote SFF_Debug, robot SFF02_Release), not yet with a new image
- Date: 2026-11-12

## Sweep

`link_sweep.ps1` is ported as post-processing (`rdt/sweep.py`): step boundaries come from the remote's `[sweep] step N gap G ms sent S`
VCP lines, or from changes of `s_tx.out.sweep_step`; robot counters are taken at the last sample before each boundary. It only observes.
The remote must run the sweep build and be reset by the user. Boundaries are PC-clock estimates (one poll period). Not verified with a real
sweep: the remote currently runs a normal build (sweep_step stays 0).

## Flashing

Programming a board is the only write path in rdt. It lives in `rdt/flash.py`, reachable from the daemon API/UI (`/api/flash/plan`,
`/api/flash/run`) and, as a dry run only, from `rdt flash-plan`. Gates for `run`: a plan with no failed check (probe attached; board DEV_ID
read over SWD equals the target's; ELF is 32-bit ARM with all segments inside the target's flash range; image path matches the target's
`allowed_images` in `targets.yaml`; image hash unchanged since planned), the exact typed phrase `FLASH <target> <sha8>`, `motors_safe` for
the robot (the user states: wheels off the ground, at the robot, able to cut power at once; 2026-11-12 change: the robot's motor power is its main supply, which
also powers the H755 Nucleo, so "power cut" is impossible while flashing), and a stopped daemon (the probe is needed exclusively). After programming, the flash is compared with the image
(`rdt/verify.py`) and a record is appended to `sessions/flash_log.jsonl`. An unreadable board fails the plan (fail closed).

Allowed images: robot `robot_s_rtos/CM7/SFF02_*/*.elf`, remote `robot_rc_rtos/SFF_*/*.elf`. So an `ATT_*` remote image or a `robot_att` image cannot
go onto this pair; change `targets.yaml` deliberately to pair other products.

Claude has no flash tool, and its permission policy denies anything outside `mcp__rdt__*` (decision 0002).

## Not done

Paired flashing (robot + remote with an `RCL_VERSION` check), CM4 images, .hex/.bin images, and a checked "reset after flash leaves the driver brake / DMKE
safe" (plan section 6: unconfirmed, debug_guide section 10 item 6). robot_s_rtos decision 0007/0008: PC10 (driver disable/brake) powers up high and `task_motor` releases it only after startup; whether the pin is held during an MCU reset by hardware is not confirmed. Flash the robot only with wheels off the ground and someone at the robot.

## Verified

Dry runs against both connected boards (read-only): the images that are flashed give PLAN OK with `already_flashed = true`; a `robot_att` image
for the robot and an `ATT_Debug` image for the remote are refused. The UI "Kiểm tra" button shows the checks and the confirm phrase. Unit tests use a fake probe and runner.
