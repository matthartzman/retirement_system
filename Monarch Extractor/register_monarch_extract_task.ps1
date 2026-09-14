<#
.SYNOPSIS
  Register/unregister the Windows Task Scheduler entry that actually runs
  the Monarch Extractor (run_monarch.ps1 -> monarch_extract.py's Playwright
  scrape against Monarch), independent of the downstream import job.

.DESCRIPTION
  Root cause of the 2026-09 outage: RetirementSystem_MonarchAutoImport (see
  ..\tools\launchers\register_monarch_autoimport_task.ps1) only reads
  whatever CSVs already exist in Monarch Extractor\output -- it has never
  been the thing that produces them. Nothing in this repo scheduled the
  extraction step itself; it only ever ran when someone launched
  run_monarch.ps1 by hand (last: 2026-09-03, then 2026-09-09). Because the
  import job treats "no new rows" as a successful no-op, that gap was
  invisible: RetirementSystem_MonarchAutoImport kept reporting success every
  day with nothing left to import.

  This script closes that gap by scheduling run_monarch.ps1 itself, timed
  to finish before RetirementSystem_MonarchAutoImport's default 4am run.
  Uses the built-in ScheduledTasks PowerShell module (New-ScheduledTaskAction
  / Register-ScheduledTask) rather than a hand-built schtasks.exe /tr
  command-line string, for the same quoting reason as the sibling launcher
  scripts (a manually quoted /tr value breaks on paths containing spaces).

  Also best-effort enables the Task Scheduler operational event log, so a
  future silent failure (e.g. a stale Monarch login session breaking the
  headless scrape) shows up in Event Viewer instead of only being
  discoverable by checking file timestamps under raw\.

  Review what this prints before trusting it against a production machine --
  it mutates OS-level scheduled tasks.

.PARAMETER Action
  Register (create/update) or Unregister (remove) the scheduled task.

.PARAMETER StartTime
  Daily run time, 24h HH:mm. Default 03:30 -- ahead of
  RetirementSystem_MonarchAutoImport's default 04:00 so a fresh extraction
  is available for that run to consume.

.EXAMPLE
  .\register_monarch_extract_task.ps1 -Action Register
.EXAMPLE
  .\register_monarch_extract_task.ps1 -Action Unregister
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Register", "Unregister")]
    [string]$Action,

    [string]$StartTime = "03:30"
)

$ErrorActionPreference = "Stop"
$TaskName = "RetirementSystem_MonarchExtract"

# This script lives directly in the Monarch Extractor folder.
$ProjectDir = $PSScriptRoot
$ScriptPath = Join-Path $ProjectDir "run_monarch.ps1"

if ($Action -eq "Unregister") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

if (-not (Test-Path $ScriptPath)) {
    throw "run_monarch.ps1 not found at $ScriptPath"
}

$PowerShellCmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
if (-not $PowerShellCmd) {
    throw "powershell.exe was not found on PATH."
}
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

Write-Host "Registering scheduled task '$TaskName' to run daily at $StartTime :"
Write-Host "  $($PowerShellCmd.Source) $Arguments"

$taskAction = New-ScheduledTaskAction -Execute $PowerShellCmd.Source -Argument $Arguments -WorkingDirectory $ProjectDir
$taskTrigger = New-ScheduledTaskTrigger -Daily -At $StartTime
# Deliberately no -Principal override here: this matches
# RetirementSystem_MonarchAutoImport's registration (default principal/logon
# type), which is the one combination already proven to run reliably,
# unattended, on this machine. monarch_extract.py's Playwright browser needs
# a real logon session for its persisted profile in monarch-browser\ to be
# usable -- if the default logon type turns out not to fire while the
# machine is locked/logged off, that's a deliberate follow-up (see the
# manual verification step this script prints below), not something to
# guess at here.
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Force | Out-Null

# Best-effort: without this log enabled, a scheduled run that fails silently
# (e.g. Monarch's session cookie in monarch-browser\ expired, so the
# headless login hangs and times out) leaves no trace beyond "task ran,
# result nonzero" -- Enable All Tasks History in Task Scheduler's own UI
# does exactly this, this is its command-line equivalent.
#
# wevtutil is an external exe, not a cmdlet: it reports failure via
# $LASTEXITCODE and its own stderr text, not a terminating exception, so
# try/catch alone does not catch (or suppress) it -- capture stderr
# explicitly and check the exit code so a permissions failure here prints
# one clear, expected note instead of a raw "Access is denied" that reads
# like the task registration itself failed.
$wevtutilOutput = & wevtutil set-log "Microsoft-Windows-TaskScheduler/Operational" /enabled:true 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Note: could not enable Task Scheduler history logging (needs an elevated/Run as Administrator shell): $wevtutilOutput"
    Write-Host "The scheduled task above was still registered successfully. Enable history manually via Task Scheduler > Enable All Tasks History if you want failure detail in Event Viewer."
}

Write-Host "Done. Verify with: schtasks /query /tn `"$TaskName`" /v /fo LIST"
Write-Host "Before trusting the schedule, run it once by hand and confirm it produces new output while running non-interactively:"
Write-Host "  schtasks /run /tn `"$TaskName`""
Write-Host "  (then check Monarch Extractor\raw\ for a new file, and 'Get-ScheduledTaskInfo -TaskName `"$TaskName`"' for LastTaskResult 0)"
