# 0009: installable app (PyInstaller folder build + Inno Setup installer)

- Status: Accepted. Build and smoke test results are recorded in `handoff/latest.md`.
- Date: 2026-11-12

## Decision

- `scripts/build_exe.ps1` builds the UI, runs PyInstaller with `scripts/robot_diag.spec` (one-folder build, windowed, entry `rdt/launcher.py`), smoke-tests the
  built exe (headless `RobotDiag.exe serve`: UI served, API answers, Claude SDK and its `claude.exe` bundled, ST-LINK scan runs) and builds
  `dist\installer\RobotDiag-Setup-<version>.exe` with Inno Setup (`scripts/installer.iss`). One-folder, not one-file: one-file unpacks hundreds of MB on every start.
- Per-user install under `%LOCALAPPDATA%\Programs\RobotDiag` (no administrator). User data goes to `%LOCALAPPDATA%\RobotDiag` (`rdt/paths.py`): `targets.yaml` seeded from the
  bundled default on first run, `sessions\`, `settings.json`, `logs\`. Uninstall and upgrade leave it alone.
- Not bundled, found and reported by the Settings page (decision 0008): STM32CubeProgrammer, the ST-LINK driver, the Claude login, the Edge WebView2 runtime (the installer warns).
  The firmware repositories are not bundled either: on another machine the ELF files are chosen in Settings.
- The file dialog is a PowerShell WinForms dialog (not tkinter, and not a child of `sys.executable`, which is the app itself in the exe).
- Version: `rdt.__version__` equals the `pyproject.toml` version (a test checks it); the installer takes it from there.

- Pins added for packaging: PyInstaller 6.22.3 and Inno Setup 6 in `scripts\toolchain.psd1`. The step-by-step guide is `docs/BUILD_DEPLOY.{vi,en}.md`; a test keeps its versions, script names and option names in line with the repository.

## Consequences

- Release steps: bump the version in both places, run `scripts/build_exe.ps1`, keep `dist\installer\...` out of git (`/dist/`, `/build/` are ignored).
- The exe is large (the Agent SDK ships its own `claude.exe`).
- The installer is not code-signed: Windows SmartScreen will warn on first run on other machines.
