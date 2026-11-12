# Legacy conversion: safeguard and rehearsal

Status: implemented 2026-11-12

The one-time conversion turns an old install's files into the plan file (`plan.rpx`). This page says what it checks, what stops it, what it copies, what it never touches, how to undo it, and how to rehearse it on a copy of a workspace first. It replaces `CONVERSION_SAFEGUARD.md` and `CONVERSION_REHEARSAL.md`.

Code: `src/legacy_conversion/` (`workspace.py` runs it, `verify.py` checks, `backup.py` copies, `steps/` holds the conversion steps), and `tools/rehearse_conversion.py` for the rehearsal. The owner approved the safeguard design at the WP10.3 checkpoint.

## Part 1. Safeguard

### Order of a run
1. Fingerprint every old file (size + SHA-256).
2. Back up the old files and check the copy (below). If the copy is wrong, stop.
3. Convert into a private staging copy of the plan. The live plan is not touched.
4. Verify the staging copy (below). Any difference stops here and the user is asked.
5. Check the old files are still byte-identical, then swap the verified copy in as one atomic
   replace; the old live plan stays beside it as `plan.rpx.pre_conversion_<time>`.
6. Only now: settings into app.db, API keys into the credential store, register and open the plan.
7. Set the done marker; keep a short result (names and counts, never values) in app.db.

A crash at any point leaves the old files as they were and the live plan either unchanged
(before 5) or wholly replaced by the verified copy (after 5); the next start finishes the rest.

### What is verified (a difference stops the conversion)
- Plan rows: what the OLD loader gave the engine (`load_csv` + migration over the same CSV set,
  or the plan's own rows if it already was a plan file) vs the converted plan.
- Engine: `parse_client` and the full projection (Roth strategy scored, as the build reports it)
  for both, to the cent.
- Tables (holdings, liabilities, HSA, targets, spending set, YTD, recovery copies): each
  converted table vs its old file, row count and every cell.
- Tier safeguard: the projection just before and just after the tier/switch mapping must be
  identical; if not, the report names the differing results and the switched features.

Warnings only (shown, never blocking): the last old build's KPIs (it ran on another date with
other prices), `input/` files that differ from the old database copy, and old
`system_config.csv` engine settings added to a plan that already lived in a plan file.

### When it stops, the user chooses
- "Convert anyway" (differences, tier safeguard, engine error): recorded in plan and result.
- "Keep my feature switches": no tier mapping, so the numbers cannot move.
- "Not now": nothing changed; the old version still works on its untouched files.
Never overridable: a failed backup, an old file that changed, a failed step, a failed swap.

### What is backed up
`backups/pre_conversion_<time>/`: `input/`, a `client_files/` folder, `system_config.csv`, the
old database (and `-wal`), old demo backups (`*.before_demo`), a picked old-format database, and
`manifest.json` (size and SHA-256 of each). Every copy is read back and compared before anything
goes live. `secrets.local.json` is copied only if the user opts in (plain-text API keys). A retry
reuses an identical verified backup.

### What is never deleted or changed
No old file is changed or deleted; the fingerprints prove it. One exception, approved in WP8.2:
the plain secrets file, only after the user confirms and every key read back from the credential
store. The result lists files this version no longer reads (`system_config.csv`, `*.before_demo`,
the `pre_conversion` plan copy) as "safe to remove after 30 days"; removing them is the user's
choice. `input/` and the old database are not listed: this version still reads them.

### Rollback
- Back to the old version: reinstall it; its files were never changed.
- Undo in the new version: close the app, delete `plan.rpx`, rename
  `plan.rpx.pre_conversion_<time>` to `plan.rpx` (none: just delete). The next start converts
  again. If in doubt about an old file, copy it back from the backup's `files/` folder.

## Part 2. Rehearsal on a copy of your workspace

Purpose: prove, on your own data and on your own machine, that converting the old files into the
new plan file (`plan.rpx`) changes nothing the engine uses. Nothing leaves your machine; the
report prints counts and names only, never values. The checks are the converter's own
(`src/legacy_conversion/verify.py`, described in Part 1).

### What the script does
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

### Steps (Windows PowerShell)
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

### Notes
- The script is Windows-safe (closes its database handles, tolerates a UTF-8 BOM in the CSVs).
- The converted `plan.rpx` in `--out` holds your plan: keep it private like the originals.
