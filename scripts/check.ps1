<#
.SYNOPSIS
    robot_diag_ui check: pytest (ELF/probe tests skip when absent) and a CLI smoke test.
#>
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$failed = @()

function Step([string]$name, [scriptblock]$body) {
    Write-Host "== $name"
    & $body
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $name" -ForegroundColor Red
        $script:failed += $name
    }
}

Push-Location $root
try {
    Step 'pytest' { & $py -m pytest -q }
    Step 'rdt --help' { & $py -m rdt.cli --help | Out-Null }
}
finally { Pop-Location }

if ($failed.Count) { Write-Host ("FAILED: " + ($failed -join ', ')) -ForegroundColor Red; exit 1 }
Write-Host 'OK'
