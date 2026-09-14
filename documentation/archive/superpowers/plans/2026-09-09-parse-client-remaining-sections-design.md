# Ticket 312 — parse_client() remaining sections: design

Design-only. No extraction code is in this change. Follows the four
already-extracted siblings (`src/parsing/daf.py`, `note_receivable.py`,
`insurance.py`, `estate_planning.py`, all merged in PR #101) and this
repo's other decomposition design doc,
`2026-09-08-deterministic-engine-stage-decomposition-design.md`, for the
risk-classification / ascending-order format.

PR #101 flagged five sections as needing "a real design pass rather than a
same-day extraction":

1. HSA Policy scalars
2. Withdrawal Policy bracket-target / spending-decline pair
3. Roth Conversion Policy
4. Allocation Optimizer inputs
5. Per-account withdrawal-order overrides

All five live inside `parse_client()` in `src/data_io.py` (2918 lines
total; `parse_client` spans lines 513–2492). Line numbers below are against
the current `main` HEAD (`8055ea2`).

## The precedent pattern (for reference)

`parse_daf(data, plan_start) -> dict` and `parse_note_receivable(data,
plan_start) -> dict`: pure functions in `src/parsing/<name>.py`, reading
only the sectioned `data` dict (`{section: {subsection: {label: value}}}`)
plus whatever already-computed scalars they need (so far, just
`plan_start`), returning a flat dict of engine-config fields that
`parse_client` merges with `c.update(...)`. They import the shared `_v`/
`_n`/`_b`/`_y` coercion helpers back from `src.data_io` (partial-circular
import, already established). `src/data_io.py` keeps a one-line
re-export (`from .parsing.daf import parse_daf`) for backward
compatibility. None of the four extracted functions are called from
`build_plan_from_json()` (the flat-JSON wizard path) — that path has its
own, simpler inline parsing of the same concepts from a flat `plan`/`a`
dict, and is out of scope for these extractions too (see each section
below for its `build_plan_from_json` mirror).

## Existing safety net

`tests/test_frozen_sample_plan_golden_master_regression.py` is a
mandatory, dollar-exact gate: it runs a realistic frozen plan (multiple
accounts, lots, liabilities, insurance) through the full `parse_client()`
→ projection engine pipeline against two pinned figures
(`PINNED_TERMINAL_NW`, `PINNED_LIFETIME_TAX`), with pricing and wall-clock
date frozen for reproducibility. `tests/test_synthetic_golden_master.py`
adds a second, input-independent golden-master leg. Both exercise every
one of the five sections below (the frozen fixture has real HSA accounts,
a Roth conversion policy, an asset allocation, and multiple withdrawal
accounts), and both would catch any behavior change from a botched
same-day extraction — not just a total-omission bug, but a subtly wrong
default or field mapping, since the pins are dollar-exact.

**This is the same kind of full-pipeline snapshot the engine-decomposition
doc had to build from scratch (that codebase had none). Here it already
exists and already covers `parse_client()`.** That materially lowers the
risk of these five extractions relative to the deterministic-engine
stages — a pure code-move that doesn't change any field's default, CSV
path, or computation will pass this gate unchanged. See each section's
"Test coverage" for the additional targeted unit/functional tests. No new
golden-master-style safety net needs to be built before starting; the
existing one is a sufficient mandatory backstop, provided each extraction
step runs the full test suite (not just the section's own targeted tests)
before being considered done.

---

## 1. HSA Policy scalars

### Exact scope

Split across **three disjoint locations** in `parse_client`, all reading
only from `data` (plus `c['plan_start']`, already computed by line 690):

- **Lines 1133–1169** — withdrawal mode/window/contribution scalars:
  `hsa_withdrawal_mode`, `hsa_annual_spend_pct`, `hsa_win_start`,
  `hsa_win_end`, `hsa_contrib_base`, `hsa_last_contrib`. Reads
  `HSA Policy > Withdrawals` and `HSA Policy > Contributions`.
- **Lines 2111–2154** — `client_hsa_schedule.csv` file load (not a `data`
  section field — a separate CSV resolved via
  `candidate_input_files(...)` / `active_workspace_id()`): produces
  `hsa_schedule_rows` (list) and `hsa_schedule_by_year` (dict keyed by
  year).
- **Lines 2228–2241** — beneficiary/death-tax-treatment scalars:
  `hsa_beneficiary_type`, `hsa_consume_by`, `hsa_expense_bank`,
  `hsa_nonqualified_treatment`, `hsa_state_conformity`. Reads
  `HSA Policy > Beneficiary` and `HSA Policy > Withdrawals`.

Output keys (11 total): `hsa_withdrawal_mode`, `hsa_annual_spend_pct`,
`hsa_win_start`, `hsa_win_end`, `hsa_contrib_base`, `hsa_last_contrib`,
`hsa_schedule_rows`, `hsa_schedule_by_year`, `hsa_beneficiary_type`,
`hsa_consume_by`, `hsa_expense_bank`, `hsa_nonqualified_treatment`,
`hsa_state_conformity`.

### Order-dependency analysis

None of the three blocks reads any other section's output — each reads
only `data` and (for the first block) `c['plan_start']`. Their current
placement (block 1 early, block 3 right after the account registry is
built at line 2219) is **historical convenience code order, not a hard
constraint** — block 3 does not read `c['account_registry']`,
`c['hsa_ids']`, or anything else built in between. The mid-file CSV load
(block 2) similarly reads no prior `c[...]` state; it only needs
`plan_start`-independent filesystem helpers already imported at module
top (`candidate_input_files`, `active_workspace_id`, `csv`, `os`).

### Downstream consumers

Purely additive — nothing later in `parse_client` itself branches on any
HSA Policy field (confirmed: no `c['hsa_...']` reads outside each field's
own definition block, other than the window-swap logic inside block 1
which is local to that block). All consumers are external: `src/hsa_schedule.py`,
`src/planning_engines.py`, `src/projection_stages/income.py`,
`src/projection_stages/deterministic_engine.py`, `src/after_tax.py`,
`src/reporting/workbook_builder.py`, `src/reporting/sheets_strategy.py`,
`src/server/app_core.py`, `src/module_catalog.py`.

### Extraction risk assessment

**Low.** Three self-contained, order-independent blocks, each purely
additive, well covered by tests (below). The only wrinkle is that block 2
does file I/O (via already-imported helpers) rather than pure `data`-dict
reads, which is a shape difference from the daf/note_receivable precedent
but not a behavioral risk.

### Recommended interface

Two functions in one new module `src/parsing/hsa_policy.py`, mirroring
the "one module can export more than one function" allowance already
implicit in the precedent (parsing submodules are organized by input
section, not strictly 1:1 with `parse_*` calls):

```python
def parse_hsa_policy(data, plan_start) -> dict:
    """Blocks 1 and 3 combined — pure `data` dict reads, no file I/O."""
    # returns hsa_withdrawal_mode, hsa_annual_spend_pct, hsa_win_start,
    # hsa_win_end, hsa_contrib_base, hsa_last_contrib,
    # hsa_beneficiary_type, hsa_consume_by, hsa_expense_bank,
    # hsa_nonqualified_treatment, hsa_state_conformity

def parse_hsa_withdrawal_schedule() -> dict:
    """Block 2 — client_hsa_schedule.csv file load."""
    # returns hsa_schedule_rows, hsa_schedule_by_year
```

Call sites: `c.update(parse_hsa_policy(data, c['plan_start']))` can move to
right after `parse_note_receivable` (both are early, both pure); the two
current call-site locations can be collapsed into one, since nothing
requires the beneficiary block to stay near the account-registry build.
`parse_hsa_withdrawal_schedule()` can stay near the liabilities-CSV load
it's textually modeled on (same pattern, adjacent code), or move next to
`parse_hsa_policy()` — either is safe; recommend leaving it where the CSV
load already sits, to minimize the diff and keep it next to the parallel
liabilities-load block it was written to mirror.

Not required to move together with any other of the five sections — no
shared state with Withdrawal Policy, Roth Conversion, Allocation
Optimizer, or the per-account override.

`build_plan_from_json()` has its own reduced HSA defaults inline (lines
2623–2630, five conservative hardcoded defaults, no schedule); leave that
path alone, matching the precedent.

### Test coverage check

Strong, dedicated coverage: `test_hsa_policy_inputs_unit.py`,
`test_hsa_withdrawal_decoupling_regression.py`,
`test_hsa_default_schedule_regression.py`,
`test_hsa_schedule_override_contract.py`,
`test_hsa_schedule_search_wiring_regression.py`,
`test_hsa_medical_deduction_double_dip_regression.py`,
`test_hsa_terminal_cliff_regression.py`,
`test_hsa_other_assets_controls_functional.py`,
`test_contingent_liability_hsa_funding_regression.py`,
`test_workspace_isolated_holdings_hsa_liabilities_regression.py`. Plus the
frozen-plan golden master (the fixture plan has real HSA accounts and a
non-default withdrawal mode). Adequate as-is for a pure-move; no
additional net needed.

---

## 2. Withdrawal Policy bracket-target / spending-decline pair

### Exact scope

**Lines 1220–1258**, two adjacent named blocks under `Withdrawal Policy`:

- **Lines 1220–1230** ("Elective Withdrawal Bracket-Target Policy"):
  `withdrawal_bracket_target_rate`, reading
  `Withdrawal Policy > Elective Withdrawal`.
- **Lines 1232–1258** ("Adoptable Spending Policy"): `spending_policy`,
  `spending_phase_decline_pct`, `spending_phase_start_age`,
  `spending_phase_end_age`, reading `Withdrawal Policy > Spending Policy`.

Output keys (5): `withdrawal_bracket_target_rate`, `spending_policy`,
`spending_phase_decline_pct`, `spending_phase_start_age`,
`spending_phase_end_age`.

### Order-dependency analysis

None — both blocks read only `data`, via the module-level `_v`/`percent_to_float`/
`_n` helpers. No reference to any earlier-computed `c[...]` value. Pure
historical code-order convenience (they sit between the liquidity-buffer
block and the Roth Conversion Policy block only because someone typed
them there).

### Downstream consumers

Purely additive within `parse_client` — no later parse_client code reads
either key. External consumers: `src/projection_stages/spending_and_rmd.py`,
`src/projection_stages/deterministic_engine.py`, `src/planning_engines.py`,
`src/local_store.py`, `src/domain_models.py`.

### Extraction risk assessment

**Low.** Smallest of the five (39 lines), single section, no external file
I/O, no cross-block coupling, textbook fit for the daf.py-style pattern.

### Recommended interface

```python
def parse_withdrawal_spending_policy(data) -> dict:
    # returns withdrawal_bracket_target_rate, spending_policy,
    # spending_phase_decline_pct, spending_phase_start_age,
    # spending_phase_end_age
```

No `plan_start` or other scalar needed — signature is `(data)` only,
simpler than the daf/note_receivable precedent. Independent of the other
four; no bundling required. `build_plan_from_json` has its own inline
mirror (lines 2704–2709, reading from its flat `a` dict) — leave as is.

### Test coverage check

`test_withdrawal_bracket_target_policy_functional.py`,
`test_adoptable_spending_policy_functional.py`,
`test_adoptable_spending_policy_unit.py`,
`test_distribution_strategy_buttons_regression.py`,
`test_ui_dependency_ordering_functional.py`. Adequate; no additional net
needed.

---

## 3. Roth Conversion Policy

### Exact scope

**Lines 1260–1377** (118 lines), under `Withdrawal Policy > Roth
Conversion`. Reads policy mode/strategy selectors, bracket/phase rates,
IRMAA-tier targeting, fixed-dollar amount, conversion caps, and a large
set of objective-weighting knobs (legacy/estate/survivor tax-risk
weights, heir filing status, discount rate).

Output keys (23): `roth_policy`, `roth_policy_lock` (**conditional** — see
below), `roth_bracket_strategy`, `roth_target_rate`, `roth_phase_rate_1`,
`roth_phase_rate_2`, `roth_phase_rate_3`, `roth_phase_count`,
`roth_irmaa_target_tier`, `roth_irmaa_target_threshold_mfj`,
`roth_fixed_amount`, `roth_max_annual_conversion_pct_of_traditional_ira`,
`roth_max_conversion_years`, `roth_objective_mode`,
`roth_headroom_usage_pct`, `roth_irmaa_headroom_usage_pct`,
`irmaa_guardrail_mode`, `roth_irmaa_cap`, `estate_tax_objective_mode`,
`roth_optimize_terminal_weight`, `roth_optimize_tax_weight`,
`roth_optimize_terminal_tax_rate`, `roth_legacy_objective_mode`,
`roth_future_tax_rate_stress_pct`, `roth_future_tax_risk_weight`,
`roth_inheritance_tax_burden_weight`, `roth_heir_ordinary_tax_rate_assumption`,
`roth_heir_filing_status`, `roth_pre_tax_bequest_penalty_pct`,
`roth_bequest_preference_bonus_pct`, `roth_survivor_tax_risk_weight`,
`roth_tax_discount_rate`.

**Important extraction detail**: `c['roth_policy_lock'] = 'USER_SELECTED'`
(line 1272) is only set when `is_explicit_user_roth_policy(c['roth_policy'])`
is true — otherwise the key is never assigned, and downstream code
(`workbook_builder.py:135`) reads it via `c.get("roth_policy_lock")`
(defaults to `None`). The extracted function's return dict must
**conditionally include** this key (present only in the true branch),
not always include it with a `None` fallback, so `c.update(...)`
reproduces "key absent" vs. "key present and None" identically.

### Order-dependency analysis

None on any other of the five sections. It reads only `data` and the
imported helpers already at module top (`normalize_roth_policy`,
`is_explicit_user_roth_policy`, `strategy_for_roth_policy`,
`normalize_irmaa_guardrail_mode`, `percent_to_float`, `_td.ROTH_POLICIES`,
`_td.IRMAA_TIERS_BASE_YEAR`). No `c['plan_start']` or other prior local
is read. Its only internal ordering constraint is intra-block: the
`_roth_bracket_strategy` default resolution (line 1277) depends on
`c['roth_policy']` and `is_explicit_user_roth_policy(...)`, both computed
earlier in the *same* block — safe inside a single function.

### Downstream consumers

Purely additive within `parse_client` (no later code in the function
reads any `roth_*` key back — confirmed by grep). All consumption is
external: `roth_ui_build_guard.py`, `workbook_builder.py`,
`result_contract.py`, `sheets_summary_builder.py`,
`sheets_qc_reference.py`, `sheets_strategy.py`, `report_compute.py`,
`deterministic_engine.py`, `planning_engines.py`, `module_catalog.py`,
`governance.py`, `after_tax.py`.

### Extraction risk assessment

**Low-medium.** Order-dependency and downstream-consumer risk are both
low (same as sections 1–2), but this is by far the largest and most
detail-dense of the five (118 lines, 23 output keys, several validated
enum fields with fallback-to-default logic, one conditional key). The
risk is transcription risk (missing a field, dropping the conditional-key
behavior, mis-copying a default) rather than structural/sequencing risk —
worth flagging up a notch from sections 1–2 for that reason, and worth an
explicit code-review checklist item to diff old vs. new field-by-field
rather than eyeballing it.

### Recommended interface

```python
def parse_roth_conversion_policy(data) -> dict:
    # returns the 23 keys above; roth_policy_lock present only when
    # is_explicit_user_roth_policy(roth_policy) is true, matching current
    # behavior exactly
```

`(data)` only — no other scalar input needed. Independent of the other
four; no bundling required, despite living in the same `Withdrawal
Policy` CSV section as items 2 and 5 — there is no shared local state,
only a shared input namespace. `build_plan_from_json` has its own much
smaller inline subset (lines 2702–2719, ~10 of the 23 fields, reduced
defaults) — leave that path alone.

### Test coverage check

`test_roth_legacy_objective_functional.py`,
`test_roth_phase_varying_conversion_unit.py`,
`test_roth_user_ui_render_fix.py`,
`test_roth_discount_rate_default_unit.py`,
`test_roth_objective_deflator_regression.py`,
`test_roth_conversion_bracket_top_fail_loud_unit.py`,
`test_roth_conversion_extended_window_past_rmd_age_functional.py`,
`test_roth_conversion_irmaa_and_aca_guardrails.py`,
`test_after_tax_roth_build_impact_functional.py`,
`test_withdrawal_roth_ui_cleanup.py`,
`test_ui_dependency_ordering_functional.py`,
`test_aca_ptc_monte_carlo_and_ss_sweep_boundaries.py`. Broad and
field-specific coverage exists for most of the 23 keys individually. Given
the field count and the one conditional-key subtlety, recommend running
the full suite (not just these targeted files) plus explicitly diffing
`parse_client(data, ...)` output dicts (old vs. new module) for a handful
of existing plan snapshots as a belt-and-suspenders check during the PR,
in addition to relying on the golden master — the golden master will
catch a *behavior* change but a diff of the raw `c` dict is a cheaper,
more targeted spotcheck for a silently-dropped default that never shows
up as an engine output (e.g. `roth_irmaa_target_threshold_mfj`, which
several code paths only touch under specific IRMAA-tier configurations
the frozen fixture may not hit).

---

## 4. Allocation Optimizer inputs

### Exact scope

**Lines 1746–1968** (223 lines, the largest section) — reads four
sections/tables (`Model Constants > Allocation`, `Asset Class
Assumptions`, `Asset Allocation Policy`, `Asset Class Optimizer
Controls`, `Asset Correlations`), including a per-asset-class loop that
merges three CSV tables together with a local closure (`_section_vals`)
and canonicalizes class names via `_ap.canonical_asset_class`.

Output keys (24): `risk_tolerance`, `asset_class_overrides`,
`asset_class_enabled`, `asset_class_selection_action`,
`asset_class_alternate_first`, `allocation_target_pct`,
`allocation_optimizer_override_pct`, `allocation_target_notes`,
`allocation_target_sum`, `allocation_selection_mode`,
`allocation_optimizer_comment`, `capital_market_config`,
`asset_correlation_overrides`, `allocation_optimizer_override_sum`,
`allocation_source_target_class` (**conditional** — only set via
`setdefault` when an alternate-asset mapping exists), `holding_period_allocation_enabled`,
`holding_period_floor_strength`, `real_loss_aware_risk_aversion`,
`real_loss_aware_weight`, `human_capital_stability`,
`concentration_employer_stock`, `concentration_real_estate`,
`concentration_business`, `glide_path`,
`inflation_sensitive_spending_pct`, `cash_target_pct`,
`allocation_coverage` (a nested dict), `cash_accumulation_tax_types`.

(That's 27 keys, not 24 — `allocation_coverage` and
`cash_accumulation_tax_types` extend past line 1968 through line 1969;
counted them in since they're the direct continuation of the same
"Allocation Optimizer Inputs" comment block with no section break before
the next named block, `Tax Provenance Registry`, at line 1970.)

### Order-dependency analysis

None on any of the other four sections. Everything read comes from
`data` plus module-level imports (`_ap`, `_ao`, both imported at file
top). The one internal wrinkle: `c['cash_target_pct']` (line 1917) is
computed from `c['allocation_target_pct']['Cash']` if present — but
that's set two lines earlier in the *same* block, so it's safe inside one
function. Similarly `c['allocation_coverage']` reads
`c.get('allocation_source_target_class')`, which was set *earlier in the
same block* (line 1876, inside the per-class loop) — also safe inside one
function, as long as the whole 1746–1968 span moves as a single unit
rather than being split.

### Downstream consumers

Purely additive within `parse_client` — nothing later in the function
reads any of these keys back. Heavy external consumption, expected given
it's a large policy surface: `server_services/config_service.py`,
`server/app_core.py`, `schema_registry.py`, `sheets_stress.py`,
`sheets_summary_builder.py`, `report_compute.py`,
`sheets_allocation_helpers.py`, `planning_engines.py`, `optimization.py`.

### Extraction risk assessment

**Low-medium**, same rationale as Roth Conversion Policy: structurally
independent (no sequencing risk, no branch-back risk), but large (223
lines) and dense (a nested per-class loop with a closure and two
conditional/derived keys). The closure `_section_vals` and the loop
variable `cls_name` need care when lifted into a standalone function
(straightforward, but another place a copy-paste slip could drop a
branch). Slightly larger transcription surface than Roth Conversion
Policy by line count, so also low-medium rather than low.

### Recommended interface

```python
def parse_allocation_optimizer_inputs(data) -> dict:
    # returns the ~27 keys above, including the conditional
    # allocation_source_target_class key exactly as today (present only
    # when an alternate-asset-class mapping exists)
```

`(data)` only. Independent of the other four sections. `build_plan_from_json`
has its own separate, smaller inline version (lines 2860–2884, reading
from a flat `a` dict with different key names in a few spots, e.g.
`allocation_targets` as an alt key) — leave alone, same precedent as the
other four.

### Test coverage check

`test_optimization_module.py`, `test_holding_period_ui_wiring_functional.py`,
`test_compact_allocation_selection_functional.py`,
`test_tlh_unit.py`, `test_asset_class_optimizer_controls_functional.py`,
`test_real_loss_holding_period_regression.py`,
`test_active_input_visibility_functional.py`,
`test_allocation_policy_cleanup_functional.py`,
`test_allocation_scenarios_functional.py`,
`test_allocation_table_and_load_path_functional.py`,
`test_allocation_ui_backfill_functional.py`,
`test_allocation_ui_mode_panels_functional.py`,
`test_allocation_mode_diagnostics_workbook_crash_regression.py`,
`test_allocation_optimizer_preview_ui_functional.py`,
`test_allocation_optimizer_toggle_functional.py`,
`test_covered_allocation_targets_functional.py`,
`test_simplified_allocation_functional.py`,
`test_max_sharpe_tangency_allocation_regression.py`,
`test_real_loss_aware_mode_regression.py`,
`test_asset_allocation_lot_guidance_functional.py`,
`test_allocation_pie_labels_functional.py`. Very broad, field-specific
coverage across nearly every key. Same recommendation as section 3: rely
on the golden master plus the targeted suite above, and additionally
diff the raw parsed `allocation_*`/`asset_class_*`/`capital_market_config`/
`allocation_coverage` sub-dicts for a couple of real plan snapshots as a
cheap spotcheck, since this section's conditional/derived keys
(`allocation_source_target_class`, `cash_target_pct`'s Cash-override,
`allocation_coverage`'s several boolean flags) are exactly the kind of
thing a full-pipeline dollar pin might not move on if the fixture plan
doesn't happen to configure an alternate-asset mapping.

---

## 5. Per-account withdrawal-order overrides

### Exact scope

**Lines 2243–2258** (16 lines, smallest of the five), under
`Withdrawal Policy > Account Order`. One output key: `account_draw_priority`
(dict, `{account_id: int priority}`), built from arbitrary account-id
labeled rows (feature #276).

### Order-dependency analysis

None — reads only `data.get('Withdrawal Policy', {}).get('Account Order', {})`.
It happens to sit textually right after the account-registry build (lines
2216–2226) and the second HSA Policy block, but does not read
`c['account_registry']`, `c['all_acct_ids']`, or any account-id list to
validate against — the account IDs are taken as free-form strings
straight from the CSV rows, with no cross-check against the registry at
parse time (validation/fallback happens downstream in
`core._apply_draw_priority` / `core.accounts()`, which silently ignores
priorities for account IDs it doesn't recognize — see that function's
docstring, lines 221–257 in `src/core.py`). So the current placement is
historical convenience code order, not a hard constraint — though moving
it *before* the account-registry build would still be safe, since nothing
here depends on the registry either way.

### Downstream consumers

Purely additive — consumed only in `src/core.py`
(`_apply_draw_priority`, called from `core.accounts()`/`draw_order()` via
`c.get('account_draw_priority')`), nowhere else in `data_io.py` and
nowhere in `parse_client` after its own definition.

### Extraction risk assessment

**Low.** The smallest, simplest, and most clearly additive of the five —
a single dict comprehension over one CSV subsection, one output key, one
external consumer with an already-documented graceful-fallback contract.

### Recommended interface

```python
def parse_account_draw_priority(data) -> dict:
    # returns {'account_draw_priority': {account_id: int}}
```

`(data)` only. Fully independent of the other four — no shared state,
and (per the analysis above) no functional need to stay adjacent to the
account-registry build, though there's no harm in leaving the call site
where it is either, since it costs nothing to move it next to
`parse_hsa_policy` for the same "keep the small, one-shot, order-independent
parsers grouped near the top of the function" tidiness if that's ever
done. Not present in `build_plan_from_json` at all (feature is CSV-only)
— no mirror to keep in sync.

### Test coverage check

No dedicated `test_withdrawal_order*` / `test_draw_priority*` /
`test_account_order*` test file exists. The only test-suite hit for the
feature's marker string is `tests/frontend/withdrawal_other_rows.test.mjs`
(a frontend UI test, not a backend parsing/engine test). This is the one
section of the five with a real coverage gap: nothing in the Python
suite directly exercises `c['account_draw_priority']` end-to-end (the
frozen golden-master fixture almost certainly uses default account-type
ordering, so it would not catch a broken override parse unless the
fixture happens to set one, which is unlikely given the fixture predates
#276). **Recommend adding a small targeted unit test for
`parse_account_draw_priority` (or the post-extraction call site) before
or alongside this extraction** — a few lines asserting the dict shape and
int coercion/skip-on-blank behavior — rather than relying solely on the
golden master, since the golden master's coverage of this one field is
unverified/likely absent. This is a cheap, narrowly-scoped addition (not
a new golden-master-style safety net), unlike the caveat noted for
sections 3 and 4.

---

## Recommended extraction order

Ascending risk, matching the engine-decomposition doc's convention. All
five are structurally independent of each other (no pair needs to move
together) — the ordering below is about front-loading the safest,
smallest wins and using them to re-confirm the pattern before tackling
the two denser sections, plus closing the one real coverage gap before
it's needed.

1. **Section 5 (per-account withdrawal-order override)** — smallest (16
   lines), simplest, single output key, but first add the missing unit
   test called out above so the extraction has real targeted coverage,
   not just the golden master's assumed-but-unverified reach. Good first
   extraction: proves the pattern still applies cleanly to a section
   outside the early part of the function.
2. **Section 2 (Withdrawal Policy bracket-target / spending-decline
   pair)** — smallest data-only section (39 lines, 5 keys), well tested,
   textbook fit for the existing daf.py pattern.
3. **Section 1 (HSA Policy scalars)** — low risk, well tested, but touches
   three separate locations in the file (two pure, one file-I/O) and
   should land as two functions in one module; slightly more moving
   pieces than 2 or 5, so sequenced after them.
4. **Section 3 (Roth Conversion Policy)** — low-medium risk: no
   sequencing/consumer risk, but the largest single-block field count
   (23 keys, one conditional) seen so far. Do this once the pattern is
   well-proven on 1, 2, and 5. Diff the parsed `c` dict against a few
   real plan snapshots in addition to running the full suite, per the
   note above.
5. **Section 4 (Allocation Optimizer inputs)** — low-medium risk, the
   largest section by line count (223+ lines) with a per-class loop and
   two conditional/derived keys. Sequence last so the reviewer and the
   extractor both have the most practice with this pattern by the time
   they hit the densest section. Same diff-the-parsed-dict
   recommendation as section 3.

No new full-pipeline safety net is needed before starting — the existing
`test_frozen_sample_plan_golden_master_regression.py` (plus
`test_synthetic_golden_master.py`) already covers `parse_client()`
end-to-end and exercises four of the five sections. The one gap is
section 5's missing targeted test, which is cheap to close as step 1
rather than a prerequisite blocking the other four.
