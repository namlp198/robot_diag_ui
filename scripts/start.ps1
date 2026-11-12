# Start robot_diag_ui: run the daemon (127.0.0.1 only), open the UI in its own app window, stop the daemon when the window closes.
# Usage: .\scripts\start.ps1 [-Port 8765] [-Browser]   (-Browser: open in the default browser instead; then stop with Ctrl+C)
param([int]$Port = 8765, [switch]$Browser)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No .venv. Run: python -m venv .venv; .venv\Scripts\python -m pip install -e .[dev]" }
if (-not (Test-Path (Join-Path $root "ui\dist\index.html"))) { Write-Warning "ui\dist is missing: run 'npm install; npm run build' in ui\ (the page will not load until then)" }
$url = "http://127.0.0.1:$Port"

# One daemon only: it owns the probes. A running daemon older than the code on disk is stopped and restarted
# (otherwise the new UI would talk to old endpoints and pages like Frames stay empty).
try { $st = Invoke-RestMethod "$url/api/status" -TimeoutSec 2; $running = $true } catch { $running = $false }
if ($running) {
    $disk = [int][math]::Floor((Get-ChildItem (Join-Path $root "rdt\*.py") | ForEach-Object { ([DateTimeOffset]$_.LastWriteTimeUtc).ToUnixTimeSeconds() } | Measure-Object -Maximum).Maximum)
    if (-not $st.code_stamp -or [math]::Abs($st.code_stamp - $disk) -gt 1) {
        Write-Host "Daemon on port $Port is older than the code on disk: restarting it."
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
        $running = $false
    }
}
$daemon = $null
if (-not $running) {
    $daemon = Start-Process -FilePath $py -ArgumentList @("-I", "-m", "rdt.cli", "serve", "--port", $Port) -WorkingDirectory $root -PassThru -WindowStyle Minimized
    $ok = $false
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 500
        if ($daemon.HasExited) { throw "daemon exited at start (exit code $($daemon.ExitCode)); run '.venv\Scripts\rdt serve' to see why" }
        try { Invoke-RestMethod "$url/api/status" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { }
    }
    if (-not $ok) { Stop-Process -Id $daemon.Id -Force; throw "daemon did not answer on $url" }
}

try {
    $edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    if ($Browser -or -not (Test-Path $edge)) {
        Start-Process $url
        if ($daemon) { Write-Host "UI at $url. Press Ctrl+C or close this window to stop the daemon."; Wait-Process -Id $daemon.Id }
    } else {
        $profile = Join-Path $env:LOCALAPPDATA "robot_diag_ui\edge_profile"   # own profile: the process lives as long as the window
        Start-Process -FilePath $edge -ArgumentList @("--app=$url", "--user-data-dir=`"$profile`"", "--no-first-run", "--window-size=1500,950") -Wait
    }
} finally {
    if ($daemon -and -not $daemon.HasExited) { Stop-Process -Id $daemon.Id -Force }   # child python of the daemon (if any) is the same process
}
