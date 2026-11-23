<#
.SYNOPSIS
  Launch the Financial Insight app's local server and open it in a browser.
#>
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
# Loopback only, behind a per-boot local token: the browser is opened with a one-time sign-in link built from the token file.
# If the always-on server is already running this just opens it.
python financial_trends_reporter\main.py
