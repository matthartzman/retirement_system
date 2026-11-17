# Re-runs the isolation gate (three modules) and the elevated worker-account suite against the INSTALLED build,
# with real per-account workers, as SYSTEM in session 0 (the way the gateway service runs). Security review
# condition 6. Run from an ELEVATED PowerShell, with the owner's approval; nothing needs a repository checkout:
#   powershell -ExecutionPolicy Bypass -File "<this checkout>\tools\run_isolation_on_installed_build.ps1"
#   (the installed copy has this script only after it is re-exported from a main that contains it)
#   options: -InstallDir C:\RetirementPlanner\app  -Filter "attacks"  -KeepVenv
# Output: C:\Windows\Temp\rpw_isolation_installed.txt (pytest) and ...\rpw_isolation_setup.txt (venv setup),
# the pytest log's tail is printed at the end.
#
# Why a separate throwaway venv: the installed venv (<InstallDir>\runtime) has no pytest and must stay clean, and
# a pytest run from the source checkout would import the SOURCE code. So pytest runs from the installed folder
# (cwd = InstallDir, so `src` and `tests` are the installed ones) using a throwaway venv built from the installed
# runtime's own Python with requirements + requirements-gateway + pytest. The gateway and every worker it starts
# use the installed venv's Python and the installed code (RETIREMENT_ISOLATION_* below). No bytecode or pytest
# cache is written into the installed folder (checked at the end).
#
# Machine-changing: creates and removes throwaway rpwtest_ accounts, their profiles and C:\rpwtest_* folders.
# It never touches C:\RetirementPlanner\data or \state (the tests refuse those paths).
param(
    [string]$InstallDir = "C:\RetirementPlanner\app",
    [string]$Filter = "",
    [switch]$KeepVenv
)
$ErrorActionPreference = "Stop"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this from an elevated PowerShell." }
$InstallDir = (Resolve-Path $InstallDir).Path
$py = Join-Path $InstallDir "runtime\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $InstallDir "runtime\python.exe" }
if (-not (Test-Path $py)) { throw "No installed Python under $InstallDir\runtime." }
foreach ($f in @("requirements.txt", "requirements-gateway.txt", "tests\test_multi_user_isolation_integration.py")) {
    if (-not (Test-Path (Join-Path $InstallDir $f))) { throw "$f is missing from $InstallDir (is it a git archive export of main?)." }
}
$leftBefore = @(Get-LocalUser | Where-Object { $_.Name -like "rpwtest_*" })
if ($leftBefore.Count) { throw "Throwaway accounts from an earlier run exist: $($leftBefore.Name -join ', '). Remove them first." }

$venv = "C:\Windows\Temp\rpw_isotest_venv"
$setup = "C:\Windows\Temp\rpw_isolation_setup.txt"
$log = "C:\Windows\Temp\rpw_isolation_installed.txt"
$basetemp = "C:\Windows\Temp\rpw_isolation_basetemp"
$script = "C:\Windows\Temp\rpw_isolation_run.cmd"
# A readable copy of the logs (the Temp files are SYSTEM-owned): worker and gateway logs are saved here before
# teardown deletes them, so a failed run can be diagnosed afterwards.
$diag = "C:\Users\Public\rpw_isolation"
Remove-Item $diag -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $diag | Out-Null
Remove-Item $log, $setup -ErrorAction SilentlyContinue
Remove-Item $venv, $basetemp -Recurse -Force -ErrorAction SilentlyContinue

"Creating the throwaway test venv (output: $setup) ..."
# Windows PowerShell 5.1 turns a native command's stderr (pip warnings) into a terminating error under "Stop".
$ErrorActionPreference = "Continue"
& $py -m venv $venv *> $setup
if ($LASTEXITCODE -ne 0) { throw "venv creation failed; see $setup" }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt") -r (Join-Path $InstallDir "requirements-gateway.txt") "pytest>=8.0,<10" "pytest-timeout>=2.3,<3" *>> $setup
if ($LASTEXITCODE -ne 0) { throw "pip install failed; see $setup" }
$ErrorActionPreference = "Stop"

$files = "tests/test_multi_user_isolation_integration.py tests/test_multi_user_isolation_routes_integration.py tests/test_multi_user_isolation_attacks_integration.py tests/test_worker_accounts_elevated_integration.py"
$k = if ($Filter) { "-k `"$Filter`"" } else { "" }
$template = @'
@echo off
set RETIREMENT_ELEVATED_TESTS=1
set RETIREMENT_ISOLATION_LAUNCHER=per-account
set RETIREMENT_ISOLATION_INSTALL_DIR=@INSTALL@
set RETIREMENT_ISOLATION_PYTHON=@PY@
set PYTHONDONTWRITEBYTECODE=1
set RETIREMENT_ISOLATION_DIAG_DIR=@DIAG@
cd /d "@INSTALL@"
"@VPY@" -m pytest -p no:cacheprovider --basetemp="@BASETEMP@" --timeout=900 @FILES@ @K@ -s -v -rfE > "@LOG@" 2>&1
'@
$body = $template.Replace("@INSTALL@", $InstallDir).Replace("@PY@", $py).Replace("@VPY@", $vpy).Replace("@BASETEMP@", $basetemp).Replace("@FILES@", $files).Replace("@K@", $k).Replace("@LOG@", $log).Replace("@DIAG@", $diag)
$body = ($body -replace "`r?`n", "`r`n")
Set-Content $script $body -Encoding ascii -NoNewline

"Running as SYSTEM (several minutes; every user's worker is a throwaway rpwtest_ account) ..."
schtasks /create /tn rpw_isolation_run /tr $script /sc once /st 00:00 /ru SYSTEM /rl HIGHEST /f | Out-Null
schtasks /run /tn rpw_isolation_run | Out-Null
Start-Sleep 10
while ((Get-ScheduledTask rpw_isolation_run).State -eq "Running") { Start-Sleep 5 }
schtasks /delete /tn rpw_isolation_run /f | Out-Null
Remove-Item $script -ErrorAction SilentlyContinue

Copy-Item $log, $setup $diag -ErrorAction SilentlyContinue
icacls $diag /grant "*S-1-5-32-545:(OI)(CI)R" /T /C /Q | Out-Null
"Readable copies of all logs: $diag"
"--- pytest tail ($log) ---"
Get-Content $log -Tail 40

"--- afterwards: leftovers (all three lists must be empty) ---"
"accounts : " + (@(Get-LocalUser | Where-Object { $_.Name -like "rpwtest_*" }).Name -join ", ")
"folders  : " + (@(Get-ChildItem C:\ -Directory -Filter "rpwtest_*" -Force -ErrorAction SilentlyContinue).Name -join ", ")
"profiles : " + (@(Get-ChildItem C:\Users -Directory -Filter "rpwtest_*" -Force -ErrorAction SilentlyContinue).Name -join ", ")
"--- installed folder must be clean (no cache or bytecode written by the run) ---"
$dirty = @(Get-ChildItem $InstallDir -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") -and $_.FullName -notlike "$InstallDir\runtime\*" -and $_.LastWriteTime -gt (Get-Date).AddHours(-2) })
if ($dirty.Count) { "written during this run: " + ($dirty.FullName -join "; ") } else { "clean" }

if (-not $KeepVenv) { Remove-Item $venv, $basetemp -Recurse -Force -ErrorAction SilentlyContinue }
"Full log: $log"
