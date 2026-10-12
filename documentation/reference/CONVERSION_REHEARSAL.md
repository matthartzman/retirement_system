# Conversion rehearsal on a copy of your workspace

Purpose: prove, on your own data and on your own machine, that converting the old files into the
new plan file (`plan.rpx`) changes nothing the engine uses. Nothing leaves your machine; the
report prints counts and names only, never values. The checks are the converter's own
(`src/legacy_conversion/verify.py`, see `CONVERSION_SAFEGUARD.md`).

## What the script does
`tools/rehearse_conversion.py <plan_copy_dir>` copies what a conversion reads from a COPY of your
workspace into a temporary folder (never `secrets.local.json`), runs the real conversion there
(backup, every step, verification, swap, registration) and prints the verification:
- sectioned data: the old loader path (`load_csv` + migration) vs the converted plan;
- engine config (`parse_client`) and full engine output (`project`), old vs converted;
- flat datasets: each converted table vs its old file, row count and every cell;
- tier mapping: the projection before vs after the tier/switch mapping (must be identical);
- warnings only: the last old build's KPIs, `input/` files that differ from the database copy.

Exit code 0 only when every blocking check matches. Your copy is never modified; the converted
plan is written to `--out` (default a temp folder that is deleted).

## Steps (Windows PowerShell)
1. Make a copy of your workspace (do not point the script at the live folder):

   ```powershell
   Copy-Item -Recurse "C:\path\to\your\workspace" "C:\rehearsal\plan_copy"
   ```

   Used when present: `input\` (the plan CSV set, holdings, liabilities, HSA schedule, spending
   and YTD files, custom CMA / correlation files), `system_config.csv`,
   `local_state\retirement_system_v10.db` (and `-wal`), `*.before_demo` backups, `plan.rpx`,
   `output\plan_summary.json`. You may also pass the `input` folder itself.

2. From the repository folder, run:

   ```powershell
   python tools\rehearse_conversion.py C:\rehearsal\plan_copy --out C:\rehearsal\converted
   ```

   Options: `--verbose-keys` (also list the NAMES of differing keys), `--skip-engine` (skip the
   slow projection runs; `parse_client` still runs), `--show-errors` (print exception messages;
   they can quote plan values, so leave it off when you share output).

3. Read the report:
   - `-- conversion: done` (or `blocked (<reason>)`), then one line per step with counts.
   - the backup line (files copied, verified).
   - one line per check: `[MATCH]`, `[DIFF ]` (with the count and NAMES of differing keys),
     `[N/A  ]`, `[SKIP ]` or `[ERROR] <check>: <ExceptionType>` (message withheld).
   - last line `RESULT: ALL MATCH` (exit code 0) or `DIFFERENCES FOUND` (exit code 1).

4. Send back: the whole printed report (it is privacy-safe) and, if the result is not
   `ALL MATCH`, the same run with `--verbose-keys`. Do not send the plan files.

## Notes
- The script is Windows-safe (closes its database handles, tolerates a UTF-8 BOM in the CSVs).
- The converted `plan.rpx` in `--out` holds your plan: keep it private like the originals.
