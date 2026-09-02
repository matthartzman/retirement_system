<#
.SYNOPSIS
  Register/unregister the Windows Task Scheduler entry for the daily 4am
  Monarch auto-import job (ticket 305).

.DESCRIPTION
  The retirement_system desktop app has no always-on background process --
  it only runs while its window is open. The 4am unattended import therefore
  needs an OS-level scheduled task to invoke
  tools\monarch_autoimport.py headlessly, independent of whether the app is
  open. This script wraps schtasks.exe so the in-app settings toggle (and a
  human, from an elevated PowerShell prompt) can register/update/remove that
  task with one call.

  Review the exact schtasks command this prints before trusting it against a
  production machine -- it mutates OS-level scheduled tasks.

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
    schtasks /delete /tn $TaskName /f
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

if (Test-Path $FrozenExe) {
    # Packaged build: the exe doubles as a script runner (see main.py's
    # frozen script-runner mode) -- run it against monarch_autoimport.py the
    # same way tools\build_workbook.py is already invoked in packaged builds.
    $TaskRun = "`"$FrozenExe`" `"$ScriptPath`" --base-dir `"$RepoRoot`""
} else {
    $PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        throw "Neither retirement_planner.exe nor python.exe was found. Install Python or build the packaged app first."
    }
    $TaskRun = "`"$PythonExe`" `"$ScriptPath`" --base-dir `"$RepoRoot`""
}

Write-Host "Registering scheduled task '$TaskName' to run daily at $StartTime :"
Write-Host "  $TaskRun"

schtasks /create /tn $TaskName /tr $TaskRun /sc daily /st $StartTime /f

Write-Host "Done. Verify with: schtasks /query /tn `"$TaskName`" /v /fo LIST"
