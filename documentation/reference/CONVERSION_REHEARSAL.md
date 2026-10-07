# Conversion rehearsal (C3 / C3b) on a copy of your plan

Purpose: prove, on your own data and on your own machine, that converting the old plan CSV set
into the new plan file (`plan.rpx`) changes nothing the engine uses. Nothing leaves your
machine; the report prints counts and names only, never values.

## What the script does
`tools/rehearse_conversion.py <plan_copy_dir>` reads a COPY of your plan, runs step C3 (CSV set to
plan rows, legacy renames once) and C3b (custom CMA / correlation files to override rows), then
compares the old path with the converted plan three ways: sectioned data, the engine-ready config
(`parse_client`), and the full engine output (`project`). Exit code 0 only when all match. The
originals are never modified (inputs are copied to a temp folder; the converted plan is written to
`--out`, default a temp folder that is deleted).

## Steps (Windows PowerShell)
1. Make a copy of your workspace (do not point the script at the live folder):

   ```powershell
   Copy-Item -Recurse "C:\path\to\your\workspace" "C:\rehearsal\plan_copy"
   ```

   The copy should contain (any missing optional file is fine):
   - `input\client_data.csv` and its parts: `client_household.csv`, `client_income.csv`,
     `client_spending.csv`, `client_assets.csv`, `client_policy.csv`,
     `client_insurance_estate.csv`, `client_business.csv`, `client_optional_functions.csv`,
     `asset_class_optimizer_controls.csv`
   - holdings, liabilities, HSA schedule, spending budget/taxonomy files, YTD files
   - optional `input\capital_market_assumptions.csv`, `input\asset_correlations.csv`
   - optional `system_config.csv`
   - (`saved_plans\*.rpx` and any old plan database are not used by this rehearsal)

   You may also pass the `input` folder itself.

2. From the repository folder, run:

   ```powershell
   python tools\rehearse_conversion.py C:\rehearsal\plan_copy --out C:\rehearsal\converted
   ```

   Options: `--verbose-keys` (also list the section/subsection/label NAMES of differing keys),
   `--skip-engine` (skip the slow full engine run), `--show-errors` (print exception messages;
   they can quote plan values, so leave it off when you share output).

3. Read the report:
   - `C3`: files read, rows written, legacy rows renamed or dropped, comment counts, skipped
     records, duplicate keys left, marker present.
   - `C3b`: override rows written per table and marker.
   - rows per section.
   - three lines `[MATCH]` or `[DIFF ]`. A `DIFF` lists how many cells/keys differ and their
     NAMES (columns or keys), no values.
   - last line `RESULT: ALL MATCH` (exit code 0) or `DIFFERENCES FOUND` (exit code 1).
   - `[ERROR] <stage>: <ExceptionType>` means a stage raised; the message is withheld.

4. Send back: the whole printed report (it is privacy-safe) and, if the result is not
   `ALL MATCH`, the same run with `--verbose-keys`. Do not send the plan files.

## Notes
- The script is Windows-safe (closes its database handles, tolerates a UTF-8 BOM in the CSVs).
- The converted `plan.rpx` in `--out` holds your plan rows: keep it private like the originals.
- Holdings, spending and YTD still read from the copied files in this release (WP6 moves them).
