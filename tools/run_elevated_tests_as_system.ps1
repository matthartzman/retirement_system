# Runs the elevated worker-account tests as SYSTEM in session 0, the way the gateway service runs.
# Run from an elevated PowerShell in the repository root:
#   powershell -ExecutionPolicy Bypass -File tools\run_elevated_tests_as_system.ps1 [-Filter "credential"]
# Output goes to C:\Windows\Temp\rpw_system_pytest.txt and is printed at the end. Machine-changing: it creates
# and removes throwaway rpwtest_ accounts and a C:\rpwtest_* folder, so run it only on the owner's say-so.
param([string]$Filter = "")
$ErrorActionPreference = "Stop"
$wt = (Get-Location).Path
$py = (Get-Command python).Source
$log = "C:\Windows\Temp\rpw_system_pytest.txt"
$script = "C:\Windows\Temp\rpw_system_run.cmd"
Remove-Item $log -ErrorAction SilentlyContinue
$k = if ($Filter) { "-k `"$Filter`"" } else { "" }
$body = "@echo off`r`nset RETIREMENT_ELEVATED_TESTS=1`r`ncd /d `"$wt`"`r`n`"$py`" -m pytest tests/test_worker_accounts_elevated_integration.py $k -s -v -rfE > $log 2>&1`r`n"
Set-Content $script $body -Encoding ascii
schtasks /create /tn rpw_system_run /tr $script /sc once /st 00:00 /ru SYSTEM /rl HIGHEST /f | Out-Null
schtasks /run /tn rpw_system_run | Out-Null
Start-Sleep 10
while ((Get-ScheduledTask rpw_system_run).State -eq "Running") { Start-Sleep 5 }
schtasks /delete /tn rpw_system_run /f | Out-Null
Remove-Item $script
Get-Content $log -Tail 40
