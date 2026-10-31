# Account-number protection: design and plan

Date: 2026-10-31. Status: design approved with the owner's decisions of 2026-10-31 (section 8); nothing built.

## 1. Goal and rule

Now that the brokerage is known, a full account number is a credential-grade identifier. **A full account number must never be stored, displayed, logged, exported, committed or pasted anywhere in or around this system. At most the last 4 digits may appear, and a plan account name is always preferred.**

Out of scope here: cash tracking in investment accounts (separate design). Protecting the plan file against a copied disk is limited to OS-level measures (section 6, decided).

## 2. What counts as an account number

- Any account, policy, loan or card number: broker accounts (Fidelity `History_for_Account_<number>`, E*Trade `-NNNN` suffixes and `XXXXX-NNNN-N` transfer references, Vanguard's per-row `Account Number` column), bank accounts, and wire/ACH references that embed one.
- Allowed: the last 4 digits, as the importer's `fidelity:1234` style hint already does. Monarch account names may carry a longer masked suffix such as `(...9972-010)`; that is accepted as is (decision 3).
- Not account numbers, and must keep working: dates, amounts, share counts, order and confirmation numbers when clearly labelled, and securities identifiers (tickers, CUSIPs, ISINs). CUSIPs can be nine digits with no letters, so a plain "long digit run" rule would damage real data; detection is therefore cue-based only (decision 2).

## 3. Where numbers can leak today (inventory)

Checked against the live plan and the repo on 2026-10-31. Counts are rows, not values; no number is quoted here.

| Surface | Finding | State |
|---|---|---|
| Broker import: account hint | Reduced to the last 4 digits at parse time (`fidelity.py`, `etrade.py`, `vanguard.py`). | Safe |
| Broker import: raw file text | Parsed, then discarded; only parsed rows are stored. | Safe |
| `broker_imports.file_name` | Stores the browser file name as is. The Fidelity name embeds the full number (3 rows). Also echoed in the preview response and income coverage. | **Leaks** |
| `broker_activity.action` / `description` | Free text from the broker. Contains transfer and wire references (about 24 rows have 8+ digit runs). | **Leaks** |
| `ytd_transactions` (`Merchant`, `Original Statement`, `Notes`) | Free text from Monarch and bank statements; payment IDs and transfer references. About 2,300 rows have 8+ digit runs, most of them Monarch ids and payment ids. | Mask cue-word account references only (decision 2); ids stay |
| Monarch account names | Show a masked suffix, for example `(...2009)`. Last 4 or a few more digits. | Accepted (decision 3) |
| Repo, tests, docs, git history | The full Fidelity number does not appear in tracked or untracked files or in history. Test fixtures use made-up numbers. | Safe now; needs a guard |
| Assistant memory notes | Held one full number. Removed 2026-10-31; a standing rule was saved. | Fixed |
| Originals in `Downloads` | The source broker files hold full numbers. | Operational: delete after import |
| Plan backups (`plan.*.rpx`) | Git-ignored but hold all the data. One was made on 2026-10-31 before the purge. | Operational: delete when no longer needed |
| Server logs, audit trail, reports, workbooks, exports, screens other than the importer | **Not yet checked.** | Unknown; phase 0 |

## 4. Design

### 4.1 One masking module, no ad-hoc regexes

New `src/account_numbers.py`, pure and dependency-free:

- `last4(value) -> str`: digits only, last four.
- `mask_text(text, *, known_ids=()) -> str`: replaces account-number-like sequences with `…NNNN` (last 4 kept).
- `contains_account_number(text, *, known_ids=()) -> bool`: used by guards and tests.
- `mask_file_name(name) -> str`: `History_for_Account_<number> (2).csv` becomes `History_for_Account_…1234 (2).csv`.

Detection is cue-based only (decision 2), so CUSIPs, amounts and payment ids are never damaged:

1. **Cue words:** digit runs next to `ACCT`, `ACCOUNT`, `A/C`, `ACC#`, `XXXX-`, `TO/FROM ACCT`, `ROUTING`, `IBAN`, or in the `XXXXX-NNNN-N` form.
2. **File names:** any digit run of 6 or more (a file name has no CUSIPs or amounts).
3. **Per-row exemption:** a digit run equal to that row's own symbol or CUSIP field is never masked.

There is no length-based fallback for free text. A number that appears with no cue is not caught by masking; the CI scan with the local list of real numbers (4.4) is the safety net for known numbers.

The module is the only place that knows these rules. Everything else calls it.

### 4.2 Mask at every way in

| Entry point | Change |
|---|---|
| Broker import (`broker_import._report`, `_commit_part`) | Mask `file_name` before it is stored or returned; mask `action` and `description` before storage. |
| Monarch auto-import and CSV upload (`ytd_tracking`) | Mask `Merchant`, `Original Statement`, `Notes` for the cue-word cases only; payment and trace ids are left alone because they are not account numbers and masking them breaks de-duplication. |
| Account Setup / account names | No change: Monarch's masked suffixes are accepted as is. |
| API responses | No change needed once stored data is clean; the guard in 4.4 proves it. |

### 4.3 Redact what is already stored

A one-time, idempotent migration (`tools/redact_account_numbers.py`) that:

1. Refuses to run without a fresh plan backup (it makes one and prints its path).
2. Re-applies the masking functions to `broker_imports.file_name`, `broker_activity.action/description` and the cue-word cases in the `ytd_transactions` text columns.
3. Prints counts only, never values.
4. Is safe to re-run (masked text stays masked).

Row keys in `broker_activity` are content hashes and are left alone; a hash of a masked row would change them, so the redaction must be applied to the displayed fields only and `row_key` left as stored.

### 4.4 Guards that keep it true

- **Unit tests** for the module with fake numbers and a CUSIP-must-survive case.
- **Regression test over the stored schema:** build a plan from the broker fixtures (which contain fake full numbers), import, and assert no 8+ digit run survives in the free-text columns or in any API response from the broker and sales endpoints.
- **Repo scan** `tools/check_no_account_numbers.py`, run in CI and **failing the build** (decision 4; no pre-commit hook): fails on cue-word number patterns and on a user-maintained list of the real numbers. The list lives outside the repo in an ignored local file, so CI can apply only the pattern part; the list part runs locally, so run the tool before pushing.
- **Log/audit scrubber:** a logging filter that passes every record through `mask_text` (cue-based), covering `_audit` payloads.

### 4.5 Screens and exports

After 4.2 the stored data is clean, so screens follow. Add the response-scan test above to cover the Sales Ledger, broker import, reconcile and report endpoints. Reports and workbooks get the same scan as part of phase 0, because they were not inspected.

## 5. Risks and trade-offs

1. **Under-masking** is the cost of cue-only detection: a number that appears with no cue word is not caught by masking. Accepted (decision 2), because length-based masking would damage CUSIPs, share counts and check numbers. The guard test and the user-maintained list catch known numbers regardless of cue.
2. **Hash changes:** masking any field that feeds `row_key` would change dedup behaviour. The design masks after the key is computed.
3. **Last-4 collisions:** two accounts at one broker can share a last 4. That is an existing property of the hint, unchanged here; the importer already asks which plan account each hint maps to.
4. **Under-delivery of "extremely secure":** masking protects against accidental exposure (screens, screenshots, logs, git, chat). It does not protect a copied plan file. See section 6.

## 6. At-rest protection of the plan file (decided)

Decision 5: **BitLocker on the drive plus keeping the workspace out of synced folders is enough.** No encrypted-database or field-encryption work.

- Confirm BitLocker is on for the drive that holds the workspace (an owner check in Windows settings; `manage-bde -status` from an administrator shell also shows it).
- Keep the workspace and every plan backup (`plan.*.rpx`) out of OneDrive and other synced or shared folders. The repo already has a guard for this (`onedrive_guard.py`); phase 4 extends it to warn when a plan file or backup sits in a synced folder.
- Delete plan backups and the original broker files in `Downloads` once they are no longer needed.

## 7. Phases

Effort and usage are relative to a 5-hour Pro-plan session; check `/usage` against these as the work proceeds.

| Phase | Work | Model / effort | Usage estimate |
|---|---|---|---|
| 0. Finish the inventory | Scan logs, audit trail, report and workbook builders, exports and the other screens for 8+ digit runs. Counts only. | Sonnet, medium | Light to moderate. **Expensive risk:** `workbook_builder.py` (1,443 lines) and `workbook_common.py` (1,161 lines) must be searched with Grep, never read whole. |
| 1. Masking module and tests | `src/account_numbers.py` with unit tests including CUSIP and cue-word cases. | Sonnet, medium | Light. |
| 2. Mask at import | Wire into broker import and the Monarch ingest paths; extend the existing importer tests. | Sonnet, medium | Moderate. Driven by the number of existing tests that assert on `file_name` and descriptions. |
| 3. Redact stored data | `tools/redact_account_numbers.py`, backup first, counts only, run on the live plan with the user present. | Opus, high (data change) | Light, but run once with care; no test-fix loop expected. |
| 4. Guards | Response-scan regression test, CI repo scan (fails the build) with a local list, logging filter, and the synced-folder warning for plan files and backups. | Sonnet, medium | Moderate. Watch the repo scan: scope it to tracked files, not `node_modules`. |
| 5. At-rest protection | Owner confirms BitLocker and keeps nothing sensitive in synced folders; delete old backups and originals. No code beyond the phase 4 warning. | none (owner task) | Trivial. |

Total for phases 0 to 4: roughly one to two working sessions. The system-architecture diagram needs regenerating (`python tools/generate_system_diagram.py`) when `src/account_numbers.py` is added.

## 8. Decisions (owner, 2026-10-31)

1. File names are masked to the last 4 digits, for example `History_for_Account_...1234 (2).csv`.
2. Detection is cue-word only, for Monarch free text and everywhere else (file names excepted: any 6+ digit run). Ids stay.
3. A masked suffix with more than 4 digits in Monarch account names is acceptable.
4. The repo scan fails CI; there is no pre-commit hook.
5. BitLocker plus keeping the workspace out of synced folders is enough; no database or field encryption.
