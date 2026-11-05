<#
.SYNOPSIS
  Put Desktop shortcuts on this PC to restart and to stop the Financial Insight server.

.DESCRIPTION
  Creates, like tools\INSTALL_DESKTOP_ICON.py does for the apps:
    "Financial Insight - Restart Server"  stops the server if it is running, then starts it hidden
    "Financial Insight - Stop Server"     stops it
  Safe to run again: existing shortcuts are replaced. -Remove deletes them.

.EXAMPLE
  .\install_server_shortcuts.ps1
  .\install_server_shortcuts.ps1 -Remove
#>
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$Icon = Join-Path $RepoRoot "frontend\assets\retirement_planner.ico"

$shortcuts = @(
    @{ Name = "Financial Insight - Restart Server"; Script = "start_trends_server.ps1"; Extra = "-Restart" },
    @{ Name = "Financial Insight - Stop Server"; Script = "stop_trends_server.ps1"; Extra = "" }
)

$shell = New-Object -ComObject WScript.Shell
foreach ($s in $shortcuts) {
    $path = Join-Path $Desktop "$($s.Name).lnk"
    if ($Remove) {
        Remove-Item $path -ErrorAction SilentlyContinue
        Write-Host "Removed $path"
        continue
    }
    $script = Join-Path $PSScriptRoot $s.Script
    # Keep the window open a few seconds so the one-line result can be read.
    $command = "& '$script' $($s.Extra); Start-Sleep -Seconds 3"
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = "powershell.exe"
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"$command`""
    $lnk.WorkingDirectory = $RepoRoot
    $lnk.WindowStyle = 1
    if (Test-Path $Icon) { $lnk.IconLocation = $Icon }
    $lnk.Description = $s.Name
    $lnk.Save()
    Write-Host "Created $path"
}
