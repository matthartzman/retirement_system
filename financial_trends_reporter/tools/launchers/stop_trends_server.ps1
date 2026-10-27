<#
.SYNOPSIS
  Stop the always-on Financial Trends server (run this at the PC).
#>
$TaskName = "FinancialTrendsReporter_Server"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
foreach ($port in 5057, 5058) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "Financial Trends server stopped."
