$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Python = "$ProjectDir\.venv\Scripts\python.exe"
$Script = "$ProjectDir\monarch_extract.py"

Set-Location $ProjectDir

# "This year" (not the 30-day default) so a category edit made in Monarch to any
# transaction in the current year flows back; with 30 days, older edits never
# arrived and the YTD charts kept the stale category.
& $Python $Script --period "This year"

if ($LASTEXITCODE -ne 0) {
    throw "Monarch extraction failed with exit code $LASTEXITCODE"
}