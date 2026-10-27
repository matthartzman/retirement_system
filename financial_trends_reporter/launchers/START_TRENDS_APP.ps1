<#
.SYNOPSIS
  Launch the financial trends reporter's local server and open it in a browser.
#>
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
# Loopback only. If the always-on server is already running this just opens the browser.
python financial_trends_reporter\main.py
