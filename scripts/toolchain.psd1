@{
    # Pinned versions. Change only with a note in decisions/.
    Python          = '3.12'
    PyElfTools      = '>=0.31'
    PyOCD           = '0.46.1'      # chosen for reads by spike S1 (decision 0001), 2026-11-12
    CubeProgrammer  = 'C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe'
    CubeProgrammerVersion = '2.20.0'   # version the flash flow was verified with (Settings reports another one, it does not block)
    PyWebView       = '6.2.1'       # native window for `rdt app` (optional extra "app"), 2026-11-12
    PyInstaller     = '6.22.3'      # packaging (scripts/build_exe.ps1), 2026-11-12
    InnoSetup       = '6'           # installer compiler ISCC.exe (scripts/installer.iss)
    AgentSdk        ='0.2.180'     # claude-agent-sdk (Python), pinned after spike S3, 2026-11-12
}
