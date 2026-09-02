<#
.SYNOPSIS
  Register/unregister the Windows Task Scheduler entry for the daily 4am
  Monarch auto-import job (ticket 305).

.DESCRIPTION
  The retirement_system desktop app has no always-on background process --
  it only runs while its window is open. The 4am unattended import therefore
  needs an OS-level scheduled task to invoke
  tools\monarch_autoimport.py headlessly, independent of whether the app is
  open. This script uses the built-in ScheduledTasks PowerShell module
  (New-ScheduledTaskAction / Register-ScheduledTask, available since
  Windows 8 / Server 2012) rather than hand-building a schtasks.exe /tr
  command-line string -- a manually quoted /tr value breaks when any path
  involved contains a space (e.g. "C:\...\Version 10\..."), because
  schtasks.exe's own command-line parsing and PowerShell's native-argument
  passing disagree about where the quoted boundaries are. The ScheduledTasks
  cmdlets take the executable and its arguments as separate parameters and
  handle the quoting internally, so this class of bug can't recur.

  Review what this prints before trusting it against a production machine --
  it mutates OS-level scheduled tasks.

.PARAMETER Action
  Register (create/update) or Unregister (remove) the scheduled task.

.PARAMETER StartTime
  Daily run time, 24h HH:mm. Default 04:00 (matches ticket 305).

.EXAMPLE
  .\register_monarch_autoimport_task.ps1 -Action Register
.EXAMPLE
  .\register_monarch_autoimport_task.ps1 -Action Unregister
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Register", "Unregister")]
    [string]$Action,

    [string]$StartTime = "04:00"
)

$ErrorActionPreference = "Stop"
$TaskName = "RetirementSystem_MonarchAutoImport"

# Repo root is two levels up from this script (tools\launchers\).
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrozenExe = Join-Path $RepoRoot "retirement_planner.exe"
$ScriptPath = Join-Path $RepoRoot "tools\monarch_autoimport.py"

if ($Action -eq "Unregister") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

if (Test-Path $FrozenExe) {
    # Packaged build: the exe doubles as a script runner (see main.py's
    # frozen script-runner mode) -- run it against monarch_autoimport.py the
    # same way tools\build_workbook.py is already invoked in packaged builds.
    $ExecutablePath = $FrozenExe
} else {
    $PythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $PythonCmd) {
        throw "Neither retirement_planner.exe nor python.exe was found. Install Python or build the packaged app first."
    }
    $ExecutablePath = $PythonCmd.Source
}
$Arguments = "`"$ScriptPath`" --base-dir `"$RepoRoot`""

Write-Host "Registering scheduled task '$TaskName' to run daily at $StartTime :"
Write-Host "  $ExecutablePath $Arguments"

$taskAction = New-ScheduledTaskAction -Execute $ExecutablePath -Argument $Arguments -WorkingDirectory $RepoRoot
$taskTrigger = New-ScheduledTaskTrigger -Daily -At $StartTime
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Force | Out-Null

Write-Host "Done. Verify with: schtasks /query /tn `"$TaskName`" /v /fo LIST"
