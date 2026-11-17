# Copies a clean `git archive` export of a git ref (default: main) over the installed app folder.
# Run from an ELEVATED PowerShell, with the owner's approval:
#   powershell -ExecutionPolicy Bypass -File "<checkout>\tools\export_main_to_install.ps1" [-Ref main] [-InstallDir C:\RetirementPlanner\app] [-DryRun] [-Force]
# What it does: exports the ref (tracked files only, no .git, no local data) to a temp folder, then robocopy /E
# onto InstallDir, never deleting anything and leaving runtime, data, input and the folder's ACLs alone.
# What it does not do: update the runtime (pip install -r requirements.txt -r requirements-gateway.txt), run the
# ACL setup/check, or migrate users. For a live server follow the operations runbook, section 5 (upgrades), which
# this is step 3 of. Files removed from the ref since the last export stay behind (no purge).
# Refuses while the gateway service runs, unless -Force.
param(
    [string]$Ref = "main",
    [string]$InstallDir = "C:\RetirementPlanner\app",
    [string]$ServiceName = "RetirementGateway",
    [switch]$DryRun,
    [switch]$Force
)
$ErrorActionPreference = "Stop"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $DryRun) { throw "Run this from an elevated PowerShell (or use -DryRun)." }
if (-not (Test-Path $InstallDir)) { throw "InstallDir $InstallDir does not exist." }
$InstallDir = (Resolve-Path $InstallDir).Path
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ErrorActionPreference = "Continue"
$sha = (git -C $repo rev-parse --verify "$Ref^{commit}" 2>$null)
$ErrorActionPreference = "Stop"
if (-not $sha) { throw "Cannot resolve '$Ref' in $repo. Run 'git fetch' first." }

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running" -and -not $Force) {
    throw "Service $ServiceName is running. Stop it first (runbook section 5, step 1) or pass -Force."
}

$tmp = Join-Path $env:TEMP ("rp_export_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory $tmp | Out-Null
try {
    "Exporting $Ref ($sha) ..."
    $tar = "$tmp.tar"
    git -C $repo archive $Ref --format=tar -o $tar
    if ($LASTEXITCODE -ne 0) { throw "git archive failed." }
    tar -xf $tar -C $tmp
    if ($LASTEXITCODE -ne 0) { throw "tar extract failed." }
    Remove-Item $tar

    $flags = @("/E", "/XD", "runtime", "data", "input", "/XF", "acl_backup*", "/NFL", "/NDL", "/NJH", "/NP")
    if ($DryRun) { $flags += "/L" }
    "Copying onto $InstallDir$(if ($DryRun) { ' (dry run, nothing written)' }) ..."
    robocopy $tmp $InstallDir @flags
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE." }

    if (-not $DryRun) {
        Set-Content (Join-Path $InstallDir "EXPORTED_FROM.txt") "$Ref $sha $(Get-Date -Format s)" -Encoding ascii
        foreach ($f in @("tools\run_isolation_on_installed_build.ps1", "tests\isolation_per_account.py")) {
            "{0}: {1}" -f $f, (Test-Path (Join-Path $InstallDir $f))
        }
    }
    "Done. Next: update the runtime and run 'acl check' if requirements or ACLs changed (runbook section 5, step 3)."
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
