<#
.SYNOPSIS
  Launch the financial trends reporter's local server and open it in a browser.
#>
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
python financial_trends_reporter\main.py
