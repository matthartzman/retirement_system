<#
.SYNOPSIS
  Start the Financial Insight (trends reporter) server at boot, with nobody logged in, and keep its Funnel up.

.DESCRIPTION
  Three modes (run from an ELEVATED PowerShell; nothing changes unless you pass -Install or -Remove):

    .\reporter_startup_task.ps1                 dry run: prints what -Install would create
    .\reporter_startup_task.ps1 -Install        registers the scheduled task "RetirementReporterStartup"
    .\reporter_startup_task.ps1 -Remove         removes it
    .\reporter_startup_task.ps1 -Run            what the task itself runs (start the server, then re-apply Funnel)

  -Install asks for your Windows password in the standard credential dialog; Windows stores it for the task. The password
  is never written to this script, a log or the command line. The task runs as you ("whether user is logged on or not"),
  at startup, and is restarted up to 3 times, a minute apart, if it stops.

  -Run starts `python financial_trends_reporter\main.py --no-open`, waits for the remote listener on 5058, then runs
  `tailscale funnel --bg --https=443 http://127.0.0.1:5058` ONLY if Funnel 443 is not already pointing there. It never touches
  the planner's 8443/10000 entries and never runs `tailscale funnel reset`.

  Unverified: whether the reporter can read your Monarch data and Windows Credential Manager entries when run without a
  console session. After installing, reboot WITHOUT logging in and check from a phone on cellular.
#>
[CmdletBinding()]
param([switch]$Install, [switch]$Remove, [switch]$Run)

$TaskName = "RetirementReporterStartup"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RemotePort = 5058
$LogDir = Join-Path $env:ProgramData "RetirementReporter"
$Self = $MyInvocation.MyCommand.Path

function Test-FunnelOk {
    try {
        $j = (& tailscale serve status --json 2>$null) | ConvertFrom-Json
        $key = $j.Web.PSObject.Properties | Where-Object { $_.Name -like "*:443" } | Select-Object -First 1
        if (-not $key) { return $false }
        return ($key.Value.Handlers.'/'.Proxy -eq "http://127.0.0.1:$RemotePort")
    } catch { return $false }
}

if ($Run) {
    New-Item -ItemType Directory -Force $LogDir | Out-Null
    $log = Join-Path $LogDir "reporter_startup.log"
    Set-Location $RepoRoot
    $python = (Get-Command python -ErrorAction Stop).Source
    $proc = Start-Process -FilePath $python -ArgumentList @("financial_trends_reporter\main.py", "--no-open") `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir "reporter_out.log") -RedirectStandardError (Join-Path $LogDir "reporter_err.log")
    "$(Get-Date -Format s) started reporter pid $($proc.Id)" | Add-Content $log
    $up = $false
    for ($i = 0; $i -lt 60 -and -not $proc.HasExited; $i++) {
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port $RemotePort -InformationLevel Quiet -WarningAction SilentlyContinue) { $up = $true; break }
        Start-Sleep -Seconds 2
    }
    "$(Get-Date -Format s) remote listener up: $up" | Add-Content $log
    if ($up -and -not (Test-FunnelOk)) {
        & tailscale funnel --bg --https=443 "http://127.0.0.1:$RemotePort" 2>&1 | Add-Content $log
        "$(Get-Date -Format s) funnel re-applied; ok now: $(Test-FunnelOk)" | Add-Content $log
    }
    $proc.WaitForExit()  # keep the task "running" so Task Scheduler restarts it if the reporter dies
    exit $proc.ExitCode
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Self`" -Run" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed $TaskName."
    return
}
if (-not $Install) {
    Write-Host "DRY RUN. -Install would register task '$TaskName': at startup, as you, whether or not you are logged on,"
    Write-Host "running: powershell -File `"$Self`" -Run   (working folder $RepoRoot)"
    Write-Host "restart on failure: 3 times, 1 minute apart; no time limit. Nothing was changed."
    return
}

$me = "$env:USERDOMAIN\$env:USERNAME"
$cred = Get-Credential -UserName $me -Message "Windows password for the reporter startup task (stored by Windows, not by this script)"
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -User $cred.UserName -Password ($cred.GetNetworkCredential().Password) -RunLevel Limited `
    -Description "Starts the Financial Insight reporter at boot and re-applies its Funnel (443 -> $RemotePort)." | Out-Null
Write-Host "Registered $TaskName. Test it without rebooting: Start-ScheduledTask -TaskName $TaskName ; then check $LogDir\reporter_startup.log"
