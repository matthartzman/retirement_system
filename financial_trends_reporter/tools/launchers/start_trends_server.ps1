<#
.SYNOPSIS
  Start the always-on Financial Insight server hidden (no browser), or restart it.

.DESCRIPTION
  -Restart stops any running server first (stop_trends_server.ps1), then starts it again.
  Without -Restart a server that is already listening is left alone. If the Task Scheduler entry from
  register_trends_server_task.ps1 exists it is started; otherwise pythonw runs main.py directly.
  Run this at the PC (the Desktop shortcut from install_server_shortcuts.ps1 calls it).
#>
param([switch]$Restart)

$ErrorActionPreference = "Stop"
$TaskName = "FinancialTrendsReporter_Server"
$Port = 5057
$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoRoot = (Resolve-Path (Join-Path $AppRoot "..")).Path

# Ask the server itself: the socket table can keep a stale listener entry for a few seconds after a stop.
function Test-Listening {
    try { Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2 | Out-Null; $true } catch { [bool]$_.Exception.Response }
}

if ($Restart) {
    & (Join-Path $PSScriptRoot "stop_trends_server.ps1")
    $until = (Get-Date).AddSeconds(10)
    while ((Test-Listening) -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 300 }
} elseif (Test-Listening) {
    Write-Host "Financial Insight server is already running on port $Port."
    exit 0
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Start-ScheduledTask -TaskName $TaskName
} else {
    $python = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python.exe -ErrorAction SilentlyContinue }
    if (-not $python) { throw "Neither pythonw.exe nor python.exe was found on PATH." }
    Start-Process -FilePath $python.Source -ArgumentList "`"$(Join-Path $AppRoot 'main.py')`" --no-open" `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden
}

$until = (Get-Date).AddSeconds(30)
while (-not (Test-Listening) -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 500 }
if (Test-Listening) { Write-Host "Financial Insight server is running on port $Port." }
else { Write-Host "The server did not start listening on port $Port within 30 seconds."; exit 1 }
