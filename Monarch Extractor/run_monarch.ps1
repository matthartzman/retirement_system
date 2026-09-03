$ErrorActionPreference = "Stop"

$ProjectDir = "C:\RetirementPlanning\Version 10\Monarch Extractor"
$Python = "$ProjectDir\.venv\Scripts\python.exe"
$Script = "$ProjectDir\monarch_extract.py"

Set-Location $ProjectDir

& $Python $Script

if ($LASTEXITCODE -ne 0) {
    throw "Monarch extraction failed with exit code $LASTEXITCODE"
}