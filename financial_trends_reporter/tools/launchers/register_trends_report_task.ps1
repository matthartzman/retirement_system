<#
.SYNOPSIS
  Register/unregister the Windows Task Scheduler entry for the weekday 5pm
  financial trends log job (ticket 306).

.DESCRIPTION
  Mirrors retirement_system's
  tools\launchers\register_monarch_autoimport_task.ps1: this app has no
  always-on background process either, so the unattended weekday-5pm log
  entry needs an OS-level scheduled task to invoke
  tools\append_trends_log.py headlessly. Uses the built-in ScheduledTasks
  PowerShell module (New-ScheduledTaskAction / Register-ScheduledTask)
  rather than a hand-built schtasks.exe /tr command-line string -- a
  manually quoted /tr value breaks when any path involved contains a space
  (e.g. "C:\...\Version 10\..."), which is exactly the bug this replaced.

  Review what this prints before trusting it against a production machine --
  it mutates OS-level scheduled tasks.

.PARAMETER Action
  Register (create/update) or Unregister (remove) the scheduled task.

.PARAMETER StartTime
  Time of day, 24h HH:mm. Default 17:00 (5pm, matching ticket 306).

.PARAMETER RetirementSystemDir
  Path to the retirement_system workspace this app reads. Defaults to this
  repo's own root (the two apps live side by side in the same repo).

.EXAMPLE
  .\register_trends_report_task.ps1 -Action Register
.EXAMPLE
  .\register_trends_report_task.ps1 -Action Unregister
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Register", "Unregister")]
    [string]$Action,

    [string]$StartTime = "17:00",
    [string]$RetirementSystemDir = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "FinancialTrendsReporter_AppendLog"

# Repo root is two levels up from this script (financial_trends_reporter\tools\launchers\).
$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoRoot = (Resolve-Path (Join-Path $AppRoot "..")).Path
if (-not $RetirementSystemDir) { $RetirementSystemDir = $RepoRoot }
$ScriptPath = Join-Path $AppRoot "tools\append_trends_log.py"

if ($Action -eq "Unregister") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

$PythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    throw "python.exe was not found on PATH. Install Python first."
}
$ExecutablePath = $PythonCmd.Source
$Arguments = "`"$ScriptPath`" --retirement-system-dir `"$RetirementSystemDir`""

Write-Host "Registering scheduled task '$TaskName' to run Mon-Fri at $StartTime :"
Write-Host "  $ExecutablePath $Arguments"

$taskAction = New-ScheduledTaskAction -Execute $ExecutablePath -Argument $Arguments -WorkingDirectory $AppRoot
$taskTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $StartTime
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Force | Out-Null

Write-Host "Done. Verify with: schtasks /query /tn `"$TaskName`" /v /fo LIST"
