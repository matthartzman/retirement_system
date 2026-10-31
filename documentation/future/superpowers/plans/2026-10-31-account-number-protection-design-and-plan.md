# Account-number protection: design and plan

Date: 2026-10-31. Status: design for review, nothing built.

## 1. Goal and rule

Now that the brokerage is known, a full account number is a credential-grade identifier. **A full account number must never be stored, displayed, logged, exported, committed or pasted anywhere in or around this system. At most the last 4 digits may appear, and a plan account name is always preferred.**

Out of scope here: cash tracking in investment accounts (separate design), and protecting the plan file against a stolen copy of the disk (section 6 covers options, but it is its own phase).

## 2. What counts as an account number

- Any account, policy, loan or card number: broker accounts (Fidelity `History_for_Account_<number>`, E*Trade `-NNNN` suffixes and `XXXXX-NNNN-N` transfer references, Vanguard's per-row `Account Number` column), bank accounts, and wire/ACH references that embed one.
- Allowed: the last 4 digits, as the importer's `fidelity:1234` style hint already does.
- Not account numbers, and must keep working: dates, amounts, share counts, order and confirmation numbers when clearly labelled, and securities identifiers (tickers, CUSIPs, ISINs). CUSIPs can be nine digits with no letters, so a plain "long digit run" rule would damage real data (section 5, risk 1).

## 3. Where numbers can leak today (inventory)

Checked against the live plan and the repo on 2026-10-31. Counts are rows, not values; no number is quoted here.

| Surface | Finding | State |
|---|---|---|
| Broker import: account hint | Reduced to the last 4 digits at parse time (`fidelity.py`, `etrade.py`, `vanguard.py`). | Safe |
| Broker import: raw file text | Parsed, then discarded; only parsed rows are stored. | Safe |
| `broker_imports.file_name` | Stores the browser file name as is. The Fidelity name embeds the full number (3 rows). Also echoed in the preview response and income coverage. | **Leaks** |
| `broker_activity.action` / `description` | Free text from the broker. Contains transfer and wire references (about 24 rows have 8+ digit runs). | **Leaks** |
| `ytd_transactions` (`Merchant`, `Original Statement`, `Notes`) | Free text from Monarch and bank statements; payment IDs and transfer references. About 2,300 rows have 8+ digit runs, most of them Monarch ids and payment ids. | **Needs classification** |
| Monarch account names | Show a masked suffix, for example `(...2009)`. Last 4 or a few more digits. | Acceptable by the rule, but see open question 3 |
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

Detection is cue-based first, length-based second, to avoid destroying CUSIPs and amounts:

1. **Cue words:** digit runs next to `ACCT`, `ACCOUNT`, `A/C`, `ACC#`, `XXXX-`, `TO/FROM ACCT`, `ROUTING`, `IBAN`, or in the `XXXXX-NNNN-N` form.
2. **File names:** any digit run of 6 or more.
3. **Per-row exemption:** a digit run equal to that row's own symbol or CUSIP field is never masked.
4. **Fallback:** a run of 10 or more digits with no decimal point and no currency sign is masked in free-text fields only, never in numeric or identifier columns.

The module is the only place that knows these rules. Everything else calls it.

### 4.2 Mask at every way in

| Entry point | Change |
|---|---|
| Broker import (`broker_import._report`, `_commit_part`) | Mask `file_name` before it is stored or returned; mask `action` and `description` before storage. |
| Monarch auto-import and CSV upload (`ytd_tracking`) | Mask `Merchant`, `Original Statement`, `Notes` for the cue-word cases only (these hold ids that are not account numbers; see open question 2). |
| Account Setup / account names | Normalise suffixes to the last 4 where more digits appear. |
| API responses | No change needed once stored data is clean; the guard in 4.4 proves it. |

### 4.3 Redact what is already stored

A one-time, idempotent migration (`tools/redact_account_numbers.py`) that:

1. Refuses to run without a fresh plan backup (it makes one and prints its path).
2. Re-applies the masking functions to `broker_imports.file_name`, `broker_activity.action/description` and, per the decision on open question 2, the `ytd_transactions` text columns.
3. Prints counts only, never values.
4. Is safe to re-run (masked text stays masked).

Row keys in `broker_activity` are content hashes and are left alone; a hash of a masked row would change them, so the redaction must be applied to the displayed fields only and `row_key` left as stored.

### 4.4 Guards that keep it true

- **Unit tests** for the module with fake numbers and a CUSIP-must-survive case.
- **Regression test over the stored schema:** build a plan from the broker fixtures (which contain fake full numbers), import, and assert no 8+ digit run survives in the free-text columns or in any API response from the broker and sales endpoints.
- **Repo scan** `tools/check_no_account_numbers.py`, run in CI and as an optional pre-commit hook: fails on cue-word number patterns and on a user-maintained list of the real numbers, kept outside the repo in an ignored local file (so the list itself is never committed).
- **Log/audit scrubber:** a logging filter that passes every record through `mask_text` (cue-based), covering `_audit` payloads.

### 4.5 Screens and exports

After 4.2 the stored data is clean, so screens follow. Add the response-scan test above to cover the Sales Ledger, broker import, reconcile and report endpoints. Reports and workbooks get the same scan as part of phase 0, because they were not inspected.

## 5. Risks and trade-offs

1. **Over-masking** damages real data (all-digit CUSIPs, large share counts, check numbers). Mitigated by cue-first detection and the per-row exemption, at the cost of missing numbers that appear with no cue and fewer than 10 digits. The guard test and the user-maintained list catch known numbers regardless of cue.
2. **Hash changes:** masking any field that feeds `row_key` would change dedup behaviour. The design masks after the key is computed.
3. **Last-4 collisions:** two accounts at one broker can share a last 4. That is an existing property of the hint, unchanged here; the importer already asks which plan account each hint maps to.
4. **Under-delivery of "extremely secure":** masking protects against accidental exposure (screens, screenshots, logs, git, chat). It does not protect a copied plan file. See section 6.

## 6. At-rest protection of the plan file (separate phase)

Options for `plan.rpx` (a SQLite file, unencrypted today):

| Option | What it protects | Cost |
|---|---|---|
| A. OS-level: BitLocker for the drive, plus keep the workspace out of OneDrive/synced folders | A lost or stolen machine | None in code; settings only. The repo already has an OneDrive guard (`onedrive_guard.py`) |
| B. SQLCipher (encrypted SQLite) with a key from the Windows credential store | A copied plan file | Large: new dependency, key handling, every tool and test that opens the file, backup and recovery |
| C. Application-level field encryption for the few sensitive columns | A copied plan file, partly | Medium, but searchable fields and tests get awkward |

Recommendation: do A now (it is free), and decide on B after phases 1 to 3, once the number of places holding identifiers has fallen to almost none. If masking removes every full number from the file, B protects far less than it appears to.

## 7. Phases

Effort and usage are relative to a 5-hour Pro-plan session; check `/usage` against these as the work proceeds.

| Phase | Work | Model / effort | Usage estimate |
|---|---|---|---|
| 0. Finish the inventory | Scan logs, audit trail, report and workbook builders, exports and the other screens for 8+ digit runs. Counts only. | Sonnet, medium | Light to moderate. **Expensive risk:** `workbook_builder.py` (1,443 lines) and `workbook_common.py` (1,161 lines) must be searched with Grep, never read whole. |
| 1. Masking module and tests | `src/account_numbers.py` with unit tests including CUSIP and cue-word cases. | Sonnet, medium | Light. |
| 2. Mask at import | Wire into broker import and the Monarch ingest paths; extend the existing importer tests. | Sonnet, medium | Moderate. Driven by the number of existing tests that assert on `file_name` and descriptions. |
| 3. Redact stored data | `tools/redact_account_numbers.py`, backup first, counts only, run on the live plan with the user present. | Opus, high (data change) | Light, but run once with care; no test-fix loop expected. |
| 4. Guards | Response-scan regression test, repo scan with a local ignore list, logging filter. | Sonnet, medium | Moderate. Watch the repo scan: scope it to tracked files, not `node_modules`. |
| 5. At-rest protection | Option A settings now; option B only if still wanted. | Opus, high | A is trivial. B is heavy (touches every plan-file opener) and should be its own plan. |

Total for phases 0 to 4: roughly one to two working sessions. The system-architecture diagram needs regenerating (`python tools/generate_system_diagram.py`) when `src/account_numbers.py` is added.

## 8. Open questions

1. Should file names be masked to the last 4 (recommended) or replaced with a generic label such as `Fidelity file 2026-10-30`?
2. Monarch free text (`Merchant`, `Original Statement`): mask only cue-word account references, or also payment and trace ids? Recommendation: cue-word only; ids are not account numbers and masking them breaks de-duplication.
3. Is a masked suffix with more than 4 digits (for example `(...9972-010)`) acceptable in Monarch account names, or should it be cut to the last 4?
4. Should the repo scan block commits (hook) or only fail CI?
5. Phase 5: is BitLocker plus keeping the workspace out of synced folders enough, or do you want the encrypted-file option scoped?
