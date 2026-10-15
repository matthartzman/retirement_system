$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Python = "$ProjectDir\.venv\Scripts\python.exe"
$Script = "$ProjectDir\monarch_extract.py"

Set-Location $ProjectDir

# "This year" (not the 30-day default) so a category edit made in Monarch to any
# transaction in the current year flows back; with 30 days, older edits never
# arrived and the YTD charts kept the stale category.
& $Python $Script --period "This year"

$TransactionsExit = $LASTEXITCODE

# Daily account balances. Independent of the transactions step: a failure in one
# must not stop the other, so both run and the exit status reports either failure.
& $Python "$ProjectDir\monarch_balances.py"
$BalancesExit = $LASTEXITCODE

# Load the fresh balances into the trends reporter's store (stdlib-only importer, so the
# extractor's venv can run it). Skipped when the export itself failed.
if ($BalancesExit -eq 0) {
    & $Python "$ProjectDir\..\financial_trends_reporter\tools\import_monarch_balances.py" --retirement-system-dir "$ProjectDir\.."
    $BalancesExit = $LASTEXITCODE
}

if ($TransactionsExit -ne 0) {
    throw "Monarch extraction failed with exit code $TransactionsExit"
}
if ($BalancesExit -ne 0) {
    throw "Monarch balances export failed with exit code $BalancesExit"
}