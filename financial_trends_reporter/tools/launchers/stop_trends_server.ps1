<#
.SYNOPSIS
  Stop the always-on Financial Insight server (run this at the PC).
#>
$TaskName = "FinancialTrendsReporter_Server"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
foreach ($port in 5057, 5058) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
# The listening socket can report owner 0 on some Windows builds, so also stop the server by its command line.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'financial_trends_reporter[\\/]main\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Financial Insight server stopped."
