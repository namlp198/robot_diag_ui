# Create a "Robot Diag" shortcut on the desktop that runs scripts\start.ps1 without a console window.
$root = Split-Path -Parent $PSScriptRoot
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Robot Diag.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$s.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $root 'scripts\start.ps1')`""
$s.WorkingDirectory = $root
$s.Description = "robot_diag_ui: daemon + UI window"
$s.Save()
Write-Host "Created $lnk"
