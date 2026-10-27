<#
.SYNOPSIS
  Launch the financial trends reporter's local server and open it in a browser.
#>
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
# --host 0.0.0.0 serves other devices on the network (needs Security/server_api_token).
python financial_trends_reporter\main.py --host 0.0.0.0
