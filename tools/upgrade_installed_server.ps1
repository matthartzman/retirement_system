# Upgrades the installed multi-user server from the owner's checkout: runbook section 5, steps 1-5, in that order.
# Self-elevates.
#   powershell -ExecutionPolicy Bypass -File tools\upgrade_installed_server.ps1
# Stops at the first failed step, including a failed fetch, ACL setup or ACL check. A stop before the export
# restarts the service; a later stop leaves it stopped and points to the rollback (runbook section 5).
param([switch]$Elevated)
$ErrorActionPreference = "Stop"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated"
    return
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$app = "C:\RetirementPlanner\app"; $state = "C:\RetirementPlanner\state"; $data = "C:\RetirementPlanner\data"
$bk = "C:\ProgramData\RetirementPlannerGateway\backups"
$PY = "$app\runtime\Scripts\python.exe"
$changed = $false  # true once the install folder has been touched: from then on, a stop means rollback, not restart
function Check([string]$what) { if ($LASTEXITCODE) { throw "$what failed (exit code $LASTEXITCODE)" } }
try {
    git -C $repo fetch origin main
    Check "git fetch origin main (nothing changed)"
    Write-Host "== 1. Stop the service" -ForegroundColor Cyan
    Set-Location $app
    & $PY -m src.gateway.service stop
    Check "service stop (nothing changed)"
    Write-Host "== 2. Full backup with the OLD code" -ForegroundColor Cyan
    & $PY -m src.gateway.ops backup run --config "$state\gateway.json"
    if ($LASTEXITCODE) {
        & $PY -m src.gateway.service start
        throw "backup failed; nothing changed and the service was started again"
    }
    Write-Host "== 3. Copy origin/main over the install, update the runtime, permissions" -ForegroundColor Cyan
    $changed = $true
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tools\export_main_to_install.ps1" -Ref origin/main -InstallDir $app
    Check "export"
    & $PY -m pip install -r "$app\requirements.txt" -r "$app\requirements-gateway.txt"
    Check "pip install"
    Set-Location $app
    $acl = @("--data-root", $data, "--gateway-db", "$state\gateway.db", "--install-dir", $app, "--backup-dir", $bk, "--gateway-sid", "S-1-5-18")
    & $PY -m src.gateway.acl setup @acl --workers-stopped  # step 1 stopped the service and so every worker (SEC-03)
    Check "acl setup"
    & $PY -m src.gateway.acl check @acl --forbid $repo
    Check "acl check (read its findings above; the service was NOT started)"
    Write-Host "== 4. Migrate users with the NEW code" -ForegroundColor Cyan
    & $PY -m src.gateway.ops migrate-all --config "$state\gateway.json" --report "$state\migrate_report.json"
    if ($LASTEXITCODE) { Write-Warning "migrate-all reported problems: read $state\migrate_report.json before starting"; throw "migration needs attention" }
    Write-Host "== 5. Start the service" -ForegroundColor Cyan
    & $PY -m src.gateway.service start
    Check "service start"
    Write-Host "Upgrade finished. Reload the app and check the health page." -ForegroundColor Green
} catch {
    Write-Host "STOPPED: $_" -ForegroundColor Red
    if ($changed) {
        Write-Host "The service is stopped and the install folder was changed. Fix the cause and run this again, or roll back (runbook section 5)." -ForegroundColor Yellow
    } else {
        Write-Host "Nothing was installed. Check the service state before running this again." -ForegroundColor Yellow
    }
}
Read-Host "Press Enter to close"
