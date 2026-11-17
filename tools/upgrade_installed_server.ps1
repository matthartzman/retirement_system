# Upgrades the installed multi-user server from the owner's checkout (runbook section 5). Self-elevates.
#   powershell -ExecutionPolicy Bypass -File tools\upgrade_installed_server.ps1
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
try {
    git -C $repo fetch origin main
    Write-Host "== 1. Full backup with the OLD code" -ForegroundColor Cyan
    Set-Location $app
    & $PY -m src.gateway.ops backup run --config "$state\gateway.json"
    if ($LASTEXITCODE) { throw "backup failed; nothing changed" }
    Write-Host "== 2. Stop the service" -ForegroundColor Cyan
    & $PY -m src.gateway.service stop
    Write-Host "== 3. Copy origin/main over the install" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tools\export_main_to_install.ps1" -Ref origin/main -InstallDir $app
    if ($LASTEXITCODE) { throw "export failed" }
    & $PY -m pip install -r "$app\requirements.txt" -r "$app\requirements-gateway.txt"
    Set-Location $app
    $acl = @("--data-root", $data, "--gateway-db", "$state\gateway.db", "--install-dir", $app, "--backup-dir", $bk, "--gateway-sid", "S-1-5-18")
    & $PY -m src.gateway.acl setup @acl
    & $PY -m src.gateway.acl check @acl --forbid $repo
    Write-Host "== 4. Migrate users with the NEW code" -ForegroundColor Cyan
    & $PY -m src.gateway.ops migrate-all --config "$state\gateway.json" --report "$state\migrate_report.json"
    if ($LASTEXITCODE) { Write-Warning "migrate-all reported problems: read $state\migrate_report.json before starting"; throw "migration needs attention" }
    Write-Host "== 5. Start the service" -ForegroundColor Cyan
    & $PY -m src.gateway.service start
    Write-Host "Upgrade finished. Reload the app and check the health page." -ForegroundColor Green
} catch {
    Write-Host "STOPPED: $_" -ForegroundColor Red
    Write-Host "The service may be stopped. See runbook section 5 (rollback)." -ForegroundColor Yellow
}
Read-Host "Press Enter to close"
