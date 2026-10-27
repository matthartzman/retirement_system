<#
.SYNOPSIS
  Register/unregister the Task Scheduler entry that keeps the Financial Trends
  server running whenever the owner is logged on to Windows.

.DESCRIPTION
  Starts financial_trends_reporter\main.py hidden (pythonw, --no-open) at logon,
  restarts it if it exits, and has no run-time limit. After an unattended reboot
  the server (and the Tailscale Funnel link) is down until the owner logs on.
  Stop it at the PC with stop_trends_server.ps1, never from a web page.

.EXAMPLE
  .\register_trends_server_task.ps1 -Action Register
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Register", "Unregister")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$TaskName = "FinancialTrendsReporter_Server"
$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoRoot = (Resolve-Path (Join-Path $AppRoot "..")).Path

if ($Action -eq "Unregister") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

$PythonCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if (-not $PythonCmd) { $PythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue }
if (-not $PythonCmd) { throw "Neither pythonw.exe nor python.exe was found on PATH." }
$Arguments = "`"$(Join-Path $AppRoot 'main.py')`" --no-open"

Write-Host "Registering '$TaskName' to run at logon for $env:USERNAME :"
Write-Host "  $($PythonCmd.Source) $Arguments"

$taskAction = New-ScheduledTaskAction -Execute $PythonCmd.Source -Argument $Arguments -WorkingDirectory $RepoRoot
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Settings $settings -Force | Out-Null
Write-Host "Done. Start it now with: Start-ScheduledTask -TaskName $TaskName"
