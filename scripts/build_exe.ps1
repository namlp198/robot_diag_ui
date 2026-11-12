# Build the installable app: UI -> PyInstaller (dist\RobotDiag\RobotDiag.exe) -> smoke test -> Inno Setup installer.
#   .\scripts\build_exe.ps1                  # everything
#   .\scripts\build_exe.ps1 -SkipUi          # reuse ui\dist (no npm)
#   .\scripts\build_exe.ps1 -NoInstaller     # only the folder build + smoke test
#   .\scripts\build_exe.ps1 -NoSmoke         # skip the smoke test
#   .\scripts\build_exe.ps1 -SkipBuild       # reuse dist\RobotDiag (only smoke test and installer)
# Needs: the .venv with the daemon, probe, chat and app extras and PyInstaller (pip install -e .[daemon,probe,chat,app] pyinstaller==6.22.3),
# Node (only to build the UI), Inno Setup 6 (ISCC.exe) for the installer.
param([switch]$SkipUi, [switch]$SkipBuild, [switch]$NoInstaller, [switch]$NoSmoke)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

# Windows PowerShell 5.1 turns anything a native tool writes to stderr (PyInstaller, npm, ISCC log there) into an error under
# $ErrorActionPreference = Stop; run such tools with it relaxed and judge them by their exit code.
function Invoke-Tool {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $args[0] @($args | Select-Object -Skip 1) 2>&1 | ForEach-Object { "$_" } | Out-Host } finally { $ErrorActionPreference = $old }
}
if (-not (Test-Path $py)) { throw "No .venv. Run: python -m venv .venv; .venv\Scripts\python -m pip install -e .[daemon,probe,chat,app] pyinstaller==6.22.3" }
$version = (& $py -I -c "import sys; sys.path.insert(0,'.'); import rdt; print(rdt.__version__)").Trim()
Write-Host "== Robot Diag $version"

if ($SkipBuild) { $SkipUi = $true }
if (-not $SkipUi) {
    Write-Host "== UI"
    Push-Location (Join-Path $root "ui")
    try {
        if (-not (Test-Path "node_modules")) { Invoke-Tool npm install; if ($LASTEXITCODE) { throw "npm install failed" } }
        Invoke-Tool npm run build
        if ($LASTEXITCODE) { throw "npm run build failed" }
    } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $root "ui\dist\index.html"))) { throw "ui\dist is missing: build the UI (run without -SkipUi)" }

if (-not $SkipBuild) {
Write-Host "== PyInstaller"
& $py -I -c "import PyInstaller" 2>$null
if ($LASTEXITCODE) { throw "PyInstaller is not installed: .venv\Scripts\python -m pip install pyinstaller==6.22.3" }
Invoke-Tool $py -m PyInstaller --noconfirm --clean --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build\pyinstaller") (Join-Path $root "scripts\robot_diag.spec")
if ($LASTEXITCODE) { throw "PyInstaller failed" }
}
$exe = Join-Path $root "dist\RobotDiag\RobotDiag.exe"
if (-not (Test-Path $exe)) { throw "build produced no RobotDiag.exe" }
$size = [math]::Round(((Get-ChildItem (Join-Path $root "dist\RobotDiag") -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB)
Write-Host "== built $exe ($size MB in the folder)"

if (-not $NoSmoke) {
    # The headless daemon from the built exe: it must start, serve the UI and the API, and find the bundled pieces.
    Write-Host "== smoke test"
    $port = 8897
    $dataDir = Join-Path $env:LOCALAPPDATA "RobotDiag"
    $p = Start-Process -FilePath $exe -ArgumentList @("serve", "--port", $port) -PassThru -WindowStyle Hidden
    try {
        $up = $false
        foreach ($i in 1..60) { Start-Sleep -Milliseconds 500; try { Invoke-RestMethod "http://127.0.0.1:$port/api/status" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { } }
        if (-not $up) { throw "the built exe did not answer on port $port (see $dataDir\logs\robot_diag.log)" }
        $html = (Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5).Content
        if ($html -notmatch "robot_diag") { throw "the bundled UI was not served" }
        $ref = Invoke-RestMethod "http://127.0.0.1:$port/api/reference" -TimeoutSec 5
        if (-not $ref.sections) { throw "/api/reference is empty" }
        $claude = Invoke-RestMethod "http://127.0.0.1:$port/api/env/claude" -TimeoutSec 30
        if (-not $claude.sdk) { throw "claude-agent-sdk is not bundled (chat would not work)" }
        $st = Invoke-RestMethod "http://127.0.0.1:$port/api/env/stlink" -TimeoutSec 60
        Write-Host ("   UI served, API ok, Claude SDK bundled (logged in: {0}), ST-LINK probes seen: {1}" -f $claude.logged_in, @($st.probes).Count)
    } finally {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process -Filter "Name='RobotDiag.exe'" | Where-Object { $_.CommandLine -match "serve --port $port" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    Write-Host "== smoke test passed"
}

if (-not $NoInstaller) {
    $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) { foreach ($c in "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") { if (Test-Path $c) { $iscc = $c; break } } }
    if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found: winget install JRSoftware.InnoSetup  (or run with -NoInstaller)" }
    Write-Host "== installer ($iscc)"
    $out = Join-Path $root "dist\installer"
    Invoke-Tool $iscc "/Qp" "/DAppVersion=$version" "/DSourceDir=$(Join-Path $root 'dist\RobotDiag')" "/DOutDir=$out" (Join-Path $root "scripts\installer.iss")
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    $setup = Get-ChildItem $out -Filter "RobotDiag-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host ("== installer: {0} ({1} MB)" -f $setup.FullName, [math]::Round($setup.Length / 1MB))
}
