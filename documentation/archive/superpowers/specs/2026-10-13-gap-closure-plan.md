# Gap-closure plan (after WP0-WP12c)

Status: implemented, except the date-driven items below (the 30-day window cleanup, unit 11.6 and the next annual tax update), which are still open. Tier 1 merged in PR #206, Tier 2 in PR #205, Tier 3 (H1 to H6) in PRs #207 to #209 (see the status tables in this file). Checked in WI-016, 2026-10-20. Earlier banner, kept for history: "draft for owner go. Nothing here is executed." Owner answers recorded 2026-10-13:
scope = all gaps, easy to hard; rental use = expected within a year (large rental items are prioritized);
capital gains in AGI and IRMAA MAGI = fix for ALL sales and re-record goldens; delivery = one session and one PR per tier.

Rules carried over: one session and one PR per tier, units as commits; CI and end-to-end only at the end of a tier;
golden compare stays green except where a unit says numbers move (then a sanctioned re-record with a changelog entry);
file-I/O enforcing audit stays green; push often (weekly usage limit); only the owner merges unless the owner says otherwise.

## Tier 0: before anything else (prerequisites, no new session)
| Item | Action |
|---|---|
| PR #204 (rental verification record) | CI must be green; one local test `test_real_workbook_has_the_rental_sheet_only_when_the_feature_is_on` failed uninvestigated: root-cause it before merge |
| PR #203 (status doc) | merge first (doc-only); #204 then updates the shared WP12 rows |
| WP12 workbook cash flow gap | WP12.7 already added "Rental Cash (net)" and "Rental Sale Tax" columns: verify it is closed and drop it from the gap list |

## Tier 1: easy (hygiene, low risk, no number changes). One PR. Sonnet, Haiku for scripted parts.
| ID | Item | Approach | Done when |
|---|---|---|---|
| E1 | `save_result_snapshot` logs a TypeError on every build (mixed-type sort keys) | give the sort a type-safe key; regression test | build log clean, snapshot content unchanged |
| E2 | `built_workbook_dir` fixture expects the workbook in the output root; builds write to `output/plans/<id>/` | point the fixture at the per-plan folder | the tests that use it pass without a legacy copy |
| E3 | unused `config_backend.append_audit_event_sqlite` | scripted reachability check, delete | enforcing audit green |
| E4 | `/code-review` at medium was never run on WP8 unit 8.4 (plan registry, demo coexistence) | run it, fix real findings only | findings fixed or answered |
| E5 | WP8 Windows parallel failure "unable to open database file" under xdist (passed on re-run, never root-caused) | reproduce with xdist on a Windows runner or via CI loop, find the shared temp path or handle; fix with per-worker paths or explicit close | 5 consecutive green Windows runs, or documented as test-isolation fix |
| E6 | `*_for_input_dir` helpers can write `<input_dir>/../plan.rpx` (stray plan file from a CLI `--base-dir`); `ytd_*` signatures still take `root`; file labels in the UI and `module_catalog` still name CSV files | refuse to create a plan file outside the live workspace (error), rename labels to dataset names, keep `root` as an alias | no stray file; labels say datasets |
| E7 | WP12.8 doubt 5: Housing Comparison has no Convert entry | note in the UI help text only | text updated |

## Tier 2: medium (small behavior changes, some design). One PR. Sonnet; Opus subagent for E8.
| ID | Item | Approach | Done when |
|---|---|---|---|
| M1 | snapshot restore does not restore rental tables | include every plan table (rental, spending, YTD, holdings) in snapshot and restore; round-trip test over all tables | restore reproduces a plan with each dataset populated |
| M2 | recovery revisions (`budget-recovery-seed`, `pre-recovery`) are exempt from pruning and would clutter a revision list | label them in the revision API and UI, add a "recovery" filter, keep them unpruned | revision list shows a labelled, collapsible group |
| M3 | build input fingerprint renders and hashes each whole dataset (including 5k+ YTD rows) on every computation | measure first; if over a threshold, add a per-dataset revision counter and hash that | time per fingerprint recorded before and after |
| M4 | header-only CSV saves drop their header (empty dataset reads as missing) | keep the column list in plan meta so an empty dataset keeps its header and rollback restores it | header-only save round-trips |
| M5 | first optimizer run in a pytest process differs by about $2.7k baseline net worth from later runs (also on old code) | find the module-level cache or state; make runs order-independent | same result on first and later runs |
| M6 | WP12.8 doubt 2: with the feature on, sell/keep candidates drop the plan's own converted-home entry; the do-nothing baseline keeps it | make the candidate set consistent and show it in the comparison notes | notes and numbers agree |
| M7 | WP12.8 doubt 3: lifetime cost uses an estimated tax on rent | use the engine's exact tax delta for rent-out candidates when cheap, else keep the estimate with a visible label | estimate labelled, or exact |

### Tier 2 status (PR #205, draft)
| ID | Status | Result |
|---|---|---|
| M1 | done | revisions keep and restore every plan table (flat datasets, rental) in `revision_datasets` as `table:<name>`; no schema bump; round-trip test over all tables; older revisions restore plan rows only |
| M2 | done | `list_revisions` adds `label` and `group` (`recovery` / `history`); `GET /api/plan/revisions?group=` returns groups with counts (recovery collapsed by default); recovery sources stay unpruned. There was no revision list in the UI to extend, so no UI change |
| M3 | measured, no change | 55 ms per dataset fingerprint (and per `plan_state`) with 5,000 YTD rows, 0.9 ms for the row revision; under the 200 ms threshold, so no revision counter. Fingerprint unchanged |
| M4 | done | a header-only save keeps the file's extra columns in `plan_meta` (`dataset.<table>.extra_columns`); revision capture/restore and blank-plan rollback keep it |
| M5 | done | cause: `LotEngine` kept a live reference to the process-wide `PRICE_CACHE`, which is cleared between runs, so the first run priced lots differently (about $2.7k). It now copies the dict. The warm-up in `test_housing_rent_out_functional.py` is gone |
| M6 | done | feature on with a converted home in the plan: the do-nothing baseline drops that entry like every candidate; `baseline.as_entered` and `comparison_notes` show the as-entered run. Off: no new keys |
| M7 | done | shortlisted rent-out rows use the engine's exact tax delta (one extra run without the converted home); rows below the shortlist keep the estimate; each row note says which |

## Tier 3: hard (new rental modelling and tax-law changes; each behind an owner/tax-preparer checkpoint). Separate unit per item, one PR for the tier or split at the owner's choice. Opus xhigh for design; Sonnet for build.
Priority order (rental use expected within a year):
| ID | Item | Why this order | Checkpoint |
|---|---|---|---|
| H1 | Capital gains in AGI, MAGI and IRMAA MAGI for ALL sales (home sales and rental sales); currently excluded | affects every plan with a sale year, including yours; owner chose "fix for all sales" | tax-preparer review of the rule and worked examples; goldens re-recorded with changelog; a before/after report of every moved number (counts and names, then values for the owner's own plan) |
| H2 | Loan link to an existing liability for a rented or converted home | prevents double-counted debt; needed for a home you convert | data model + UI mock review |
| H3 | Personal-use reversion (rent, then move back in) and the section 121 clock, depreciation already taken | common within a year of converting | worked examples |
| H4 | Owner split between spouses and proceeds split at sale | needed for any jointly titled property | worked examples |
| H5 | Death handling: step-up in basis, release of suspended losses on the final return, and the estate-sale case where suspended losses are dropped today (IRC 469(g)(2)) | lower likelihood, high complexity | tax-preparer review |
| H6 | Optimizer search "rent out, then sell in year X" (WP12.8 doubt 1) | builds on H1 to H4 | owner review of the comparison view |

## Date-driven items (not part of the tiers)
| When | Item |
|---|---|
| about 2026-11-11 | the 30-day window ends: remove `system_config.csv`, `*.before_demo` and the pre-conversion plan copy; the pre-conversion backups may then go if the owner agrees |
| after the window and every install converted | unit 11.6: delete `legacy_conversion/` (a later release) |
| next annual tax update | re-check the rental constants, Table A-6 and passive-loss thresholds for 2026 (the verification covers 2025 rules only; see the runbook) |

## Cost and order (estimates from earlier sessions)
- Tier 1: roughly $5 to $15, a few hours. Tier 2: roughly $15 to $35. Tier 3: roughly $60 to $120 in total, spread across H1 to H6.
- Run one tier at a time. Stop after any tier. After Tier 1, Tier 2 and H1, the plan is in good shape even if H2 to H6 wait.

### Tier 3 status (PR A, draft)
| ID | Status | Result |
|---|---|---|
| H1 | done (checkpoint approved 2026-10-13) | `documentation/reference/CAPITAL_GAINS_IN_AGI.md`; engine change in `deterministic_engine.py`; no golden has a sale so none moved, changelog entry added; test `tests/test_capital_gains_in_agi_functional.py` |
| H2 | done (checkpoint approved 2026-10-13) | `loan_liability_id` on a rental (schema v10); standalone: the liability row is the one source of the loan; converted home: linked interest to Schedule E at the rented share; `RENTAL_TAX_RULES.md` section 9; `tests/test_rental_loan_link_functional.py` |
| H3 | done (checkpoint approved 2026-10-13) | `moves_back_in`, `reversion_month` (schema v11); move-back restarts the 121 clock, stops depreciation at the move-back month, rental days are nonqualified use after the 1250 split; `RENTAL_TAX_RULES.md` section 10; `tests/test_rental_reversion_functional.py` |
| H4 | done (checkpoint approved 2026-10-13) | `member_1_share` (schema v12), owner parsed, sale proceeds split by ownership with survivor and fallback rules, owner in row data and editor; `RENTAL_TAX_RULES.md` section 11; `tests/test_rental_owner_split_functional.py`; workbook Owner column not built |
| H5 | done (tax preparer approved 2026-10-13) | step-up by decedent share, depreciation restart, 469(g)(2) release on the final return, converted-home estate-year release; owner Not set keeps today's behaviour; `RENTAL_TAX_RULES.md` section 12; `tests/test_rental_death_functional.py` |
| H6 | done (owner approved the comparison 2026-10-13; shares the Sell window) | `rent_then_sell` disposition in the housing optimizer (candidates, plan variant, notes, exact tax delta without the sale tax); `RENTAL_TAX_RULES.md` section 13; `tests/test_housing_rent_then_sell_functional.py` |
