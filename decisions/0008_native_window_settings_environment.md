# 0008: native window, environment checks, ELF and firmware files in Settings

- Status: Accepted. Verified: native window starts and stops the daemon, Settings page and endpoints on this machine (Cube CLI, ST-LINK scan, Claude status), flash plan for registered .bin/.hex with fake probes. **Not run**: a real flash of a .bin/.hex, the `claude auth login` button, the native file dialog (tkinter, needs a person).
- Date: 2026-11-12

## Decision

- **`rdt app`** (`rdt/app.py`, extra `app` = pywebview 6.2.1 on the Edge WebView2 runtime): the same UI in its own window. It attaches to a daemon that already answers on the port, otherwise runs the daemon in-process and stops it when the window closes. `scripts/start.ps1` uses it by default and falls back to the Edge app window when pywebview is missing (`-Edge` forces the fallback). Theme, language and expressions persist in the WebView profile under `%LOCALAPPDATA%\robot_diag_ui\webview`.
- **Settings > Environment** (`rdt/envcheck.py`): STM32_Programmer_CLI is searched in the configured path, `PATH`, the default install and CubeIDE's bundled copies, and reported Ready with its version (the flash flow was verified with 2.20.0; another version only gets a note). The chosen path is stored and used by the flash command and the Programmer CLI page. ST-LINK drivers are checked through the Windows device list (PnP devices with VID 0483, their driver provider and version, driver packages in the driver store) with no libusb or pyOCD access, each probe is matched to a board by its serial; "none found" and "driver not working" are reported separately. Claude login uses `claude auth status` of the bundled CLI; the button runs `claude auth login` in its own console window (browser login, the app never sees credentials) and the page polls until it is logged in.
- **ELF files per board**: the user adds ELF files (native dialog or a typed path; checked: exists, 32-bit ARM, DWARF present or not) and picks one for variables (must have DWARF) and optionally one for the flashed image. The choice overrides `elf` / `image_elf` of targets.yaml in memory (`Hub.apply_settings`), takes effect at the next "Start reading", and is kept in `sessions/settings.json`.
- **Firmware files for flashing, per board**: .elf, .hex and .bin (`rdt/firmware.py`: Intel HEX parser with checksums, ELF/HEX/BIN loaders). A file registered for a board in Settings is allowed for that board's flash plan in addition to the `allowed_images` globs; a .bin needs a start address (default: start of the board's flash, multiple of 4). All other gates stay: DEV_ID, flash range, image hash, exact confirmation phrase, `motors_safe`, stopped daemon; the verification after programming compares the flash with the file's own bytes. Registration is a UI action (`PUT /api/settings`); the chat has no tool for it and cannot flash. This replaces the earlier "ELF only" limit of decision 0003.
- **Native file dialog**: `POST /api/dialog/open` runs a tkinter dialog in a separate process on the machine of the daemon (this is a local tool; loopback and Host/Origin checks apply) and returns the chosen path only.

## Consequences

- `sessions/settings.json` now holds paths of local files; it is git-ignored with the rest of `sessions/`.
- The CM4 image and paired flashing are still not supported; a .bin or .hex outside the board's `flash_range` is refused.
- Python tools that rewrite repo files must not add a BOM: `pyproject.toml` once broke that way (use UTF-8 without BOM).
