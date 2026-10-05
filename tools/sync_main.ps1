# Fast-forward the local checkout's main from origin/main -- only when that is safe.
#
# Why: pull requests merged on GitHub (e.g. by cloud sessions) land on origin/main
# only; the local checkout does not change until it is pulled.
#
# Safe by construction: it never merges, rebases, resets, or touches uncommitted
# work. It skips unless the branch is main, no git operation is in progress, the
# tree has no tracked changes, and local main has no commits origin lacks.
# Runs plain git (no model), so it uses no Claude credits.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\sync_main.ps1 [-Quiet]
# Log:   %LOCALAPPDATA%\RetirementPlanner\sync_main.log
param([switch]$Quiet)

$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA 'RetirementPlanner'
$log = Join-Path $logDir 'sync_main.log'
New-Item -ItemType Directory -Force $logDir | Out-Null

function Say([string]$msg) {
    Add-Content -Path $log -Value ("{0}  {1}" -f (Get-Date -Format 's'), $msg)
    if (-not $Quiet) { Write-Output "sync_main: $msg" }
}

trap { Say "error: $($_.Exception.Message)"; exit 0 }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Say 'skip: git not found on PATH'; exit 0 }
Set-Location $repo
$branch = (git rev-parse --abbrev-ref HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { Say 'skip: not a git repository'; exit 0 }
if ($branch -ne 'main') { Say "skip: on '$branch', not main"; exit 0 }

$gitDir = (git rev-parse --git-dir)
foreach ($f in 'index.lock', 'MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD') {
    if (Test-Path (Join-Path $gitDir $f)) { Say "skip: git operation in progress ($f)"; exit 0 }
}

git fetch origin main --quiet 2>$null
if ($LASTEXITCODE -ne 0) { Say 'skip: fetch failed (offline?)'; exit 0 }

$behind = [int](git rev-list --count HEAD..origin/main)
$ahead = [int](git rev-list --count origin/main..HEAD)
if ($behind -eq 0) { Say 'up to date'; exit 0 }
if ($ahead -gt 0) { Say "skip: $behind behind but $ahead local commit(s) not on origin (diverged); pull manually"; exit 0 }
if (git status --porcelain --untracked-files=no) { Say "skip: $behind commit(s) behind but the tree has uncommitted changes"; exit 0 }

git merge --ff-only origin/main --quiet 2>$null
if ($LASTEXITCODE -eq 0) { Say "fast-forwarded main by $behind commit(s) to $(git rev-parse --short HEAD)" }
else { Say 'skip: fast-forward refused' }
exit 0
