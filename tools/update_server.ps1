# Updates the installed multi-user server from origin/main in one go: brings this working copy up to date,
# runs tools\upgrade_installed_server.ps1 (stop, back up, install, permissions, migrate, start), then checks the result.
# Self-elevates. Run it from the desktop shortcut "Update Retirement Server" (made by tools\INSTALL_DESKTOP_ICON.py) or:
#   powershell -ExecutionPolicy Bypass -File tools\update_server.ps1
# Part A changes nothing if it stops (dirty tracked files, not on main, fetch or fast-forward failed).
# Part B is the repo's upgrade script; on a stop it prints STOPPED and its rollback hint (runbook section 5).
# Part C judges the result by itself, so it is meaningful whichever way B ended.
param([switch]$Elevated)
$ErrorActionPreference = "Continue"       # native commands: judge by exit code, not by stderr text
$repo  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$app   = "C:\RetirementPlanner\app"
$state = "C:\RetirementPlanner\state"
$key   = "C:\ProgramData\RetirementPlannerGateway\keys\backup.key"
$PY    = "$app\runtime\Scripts\python.exe"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated"
    return
}
try {
    Write-Host "== A. Update the working copy" -ForegroundColor Cyan
    Set-Location $repo
    $branch = (git rev-parse --abbrev-ref HEAD)
    if ($branch -ne "main") { throw "the working copy is on '$branch', not main; switch to main first (nothing was changed)" }
    if (git status --porcelain --untracked-files=no) { throw "tracked files have uncommitted changes; commit or stash them first (nothing was changed)" }
    git fetch origin main
    if ($LASTEXITCODE) { throw "git fetch failed (nothing was changed)" }
    git merge --ff-only origin/main
    if ($LASTEXITCODE) { throw "cannot fast-forward main (local commits that origin does not have?); not upgrading (nothing was changed)" }
    Write-Host ("Working copy is at " + (git rev-parse --short HEAD)) -ForegroundColor Green

    Write-Host "== B. Upgrade (stop, back up, install, permissions, migrate, start)" -ForegroundColor Cyan
    & "$repo\tools\upgrade_installed_server.ps1" -Elevated
    # that script ends with "Upgrade finished" or a red STOPPED: line and waits for Enter; the checks below decide

    Write-Host "== C. Checks" -ForegroundColor Cyan
    Set-Location $app
    $ok = $true
    $status = & $PY -m src.gateway.service status
    Write-Host $status
    if ("$status" -notmatch "RUNNING") { $ok = $false; Write-Warning "the service is not RUNNING" }

    $code = & $PY -c "from src.gateway.store import SCHEMA_VERSION; print(SCHEMA_VERSION)"
    $db   = & $PY -c "import sqlite3; print(sqlite3.connect(r'$state\gateway.db').execute('PRAGMA user_version').fetchone()[0])"
    Write-Host "schema: code $code, database $db"
    if ("$code" -ne "$db") { $ok = $false; Write-Warning "the database schema does not match the code" }

    & $PY -m src.gateway.ops key check --config "$state\gateway.json"
    if ($LASTEXITCODE) { $ok = $false; Write-Warning "key check failed" }
    icacls $key

    & $PY -m src.gateway.ops health --config "$state\gateway.json"
    if ($LASTEXITCODE) { $ok = $false; Write-Warning "health reported a problem" }

    $web = try { (Invoke-WebRequest http://127.0.0.1:5065/api/auth/session -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ }
    Write-Host "the gateway answers with HTTP $web (401 is expected: no session)"
    if ("$web" -ne "401") { $ok = $false; Write-Warning "unexpected answer from the gateway" }

    if ($ok) { Write-Host "ALL CHECKS PASSED" -ForegroundColor Green }
    else     { Write-Host "SOMETHING NEEDS ATTENTION: read the lines above" -ForegroundColor Red }
} catch {
    Write-Host "STOPPED: $_" -ForegroundColor Red
}
Read-Host "Press Enter to close"
