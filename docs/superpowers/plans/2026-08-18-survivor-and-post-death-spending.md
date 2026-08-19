# Survivor and post-death spending — implementation plan

**Goal:** Make household spending respond to mortality. Today it does not: `spend_base_yr` is
identical whether both members are alive, one is alive, or both are dead.

**Origin:** found while investigating Monte Carlo horizon truncation on the HSA branch
(2026-08-18). Not an HSA problem — a spending/mortality problem that blocks the horizon fix.

**Branch:** `worktree-survivor-estate-spending`, off `origin/main` @ `c79d805`. Deliberately
separate from the HSA optimizer branch so this change's golden-master movement is attributable.

## What is actually broken

Measured on the frozen fixture (`h_death_yr=2054`, `w_death_yr=2056`):

| component | 2054 both alive | 2055 survivor | 2057 both dead |
|---|---:|---:|---:|
| `spend_base_yr` | 134,976 | **134,976** | **134,976** |
| `housing_total_yr` | 132,355 | 135,139 | 83,726 |
| `wellness_base_yr` | 137,267 | 72,282 (0.53) | 0 |

- **Core spending never responds to death at all** — not to the first, not to the second.
- **Wellness is already per-person** and halves correctly, so it must NOT receive a survivor
  factor on top or the reduction compounds (0.53 × 0.65 ≈ 0.34 of joint — wrong).
- Past the second death the plan keeps charging core spending and housing indefinitely, and
  reports an `unfunded_gap` of 232,874 by 2065 for a household that no longer exists.
- The home (`home_val` 3.9M by 2074) is never sold; `home_sale_net` stays 0 forever while the
  plan pays ~85k/yr to carry it.

**Blast-radius note, corrected during implementation.** In a *default* plan
`plan_end = max(h_death_yr, w_death_yr)` — the second death year itself — so there are **no
both-dead rows**, and S2 (estate-mode spending) is genuinely **latent** on a default horizon.

**S3 (the home sale) is NOT latent, and the plan was wrong to assume so.** The sale trigger is
`year == second_death_yr`, and that year is *always* inside `plan_start..plan_end` by
construction — it IS `plan_end`. So the home sale fires on every default-horizon plan, moving
the golden master even before the horizon is ever extended. Measured on the frozen fixture:
terminal NW moves an additional −143,676.84 beyond S1 alone (selling costs), lifetime tax
+12,306.35 (sale proceeds begin generating taxable investment income in a Trust account a year
earlier than illiquid home equity would have). Both are the modeled reality of your "sell at
second death" decision, not a defect — flagged here because it changes what S4 must regenerate
and explain.

## Decisions (from the user, 2026-08-18)

1. Post-second-death rows are **estate-only** — no living expenses of any kind.
2. The home is **sold at second death**; carrying costs stop, net proceeds land in the estate.
3. A **survivor spending factor** applies to all spending **except housing**.
4. **Wellness is excluded** as well, because it already scales per-person (controller surfaced;
   user confirmed).
5. Factor default **0.65**, as a schema input so it stays adjustable per household.
6. Lands on its own branch off `main`, not on the HSA branch.

### Controller decisions, recorded for review rather than asked

- `lump_yr` (one-time planned purchases) and `business_expenses_yr` get **no** survivor factor —
  neither is per-capita household consumption. Both **do** go to zero at second death.
- `ltc_prem_yr` gets no factor; it is a per-person premium and follows the wellness treatment.

## Direction of the movement — pin this at regeneration

Today the survivor effectively spends at **1.00**. Moving to **0.65** *reduces* spending, so
terminal net worth and success rates **go up**. A change that makes plans look better deserves
more scrutiny than one that makes them look worse, not less — the regeneration entry must state
the direction and the cause explicitly, and the acceptance test must pin the survivor-year
spending directly rather than inferring it from the terminal figure.

## Global Constraints

- `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` on **every** test run.
- Capture pytest output to a FILE and read it; a trailing `; echo "exit=$?"` reports the *echo's*
  status. That mistake has produced a false green three times in this project.
- This repo's `-q` config prints no final "N passed" line. Exit 0 with no `^FAILED`/`^ERROR` is clean.
- Do **not** run `-n auto` here — it yields resource-contention failures. Run serially.
- After any broad run, `git status` and revert unintended changes, notably
  `tools/js_codemod/census_report.json`.
- **Line endings:** `core.autocrlf=true` globally but blobs are mixed —
  `src/planning_engines.py` is CRLF, `src/projection_stages/deterministic_engine.py` is LF. A plain
  `git add` renormalizes and produces a huge phantom diff. Check `git diff --stat` before committing.
- Every new guard must be demonstrated failing before it is trusted.
- Do not re-pin the golden master until Task S4.

## Anchors

- `h_alive = year <= c['h_death_yr']` — `deterministic_engine.py:545`
- alive-counting idiom already in use — `hsa_people_eligible`, `:901`
- `row['spend_base_yr'] = spend` — `:1040`
- `total_spend_need = (...)` — `:1405`, and a second assembly at `:1565`
- existing death hook — `apply_death_transition`, `:569`
- existing home-sale machinery — `home_sale_net` / `home_sale_costs` / `home_sale_gain` /
  `home_sale_tax` row keys; second-death step-up already in `after_tax.py`
- current pins — `PINNED_TERMINAL_NW = 5824239.30`, `PINNED_LIFETIME_TAX = 1290848.91`

---

## Task S1 — survivor spending factor

**Model · effort: opus · medium.** Small surface, moves every client dollar.

- Add `survivor_spend_factor` to `reference_data/schema.csv` (Household), default `0.65`,
  range 0–1, described as applying to non-housing, non-healthcare living expenses.
- Parse onto `c['survivor_spend_factor']` in `data_io.py`.
- In `deterministic_engine.py`, derive `n_alive` from the existing `h_alive`/`w_alive` locals
  using the `:901` idiom. When exactly one is alive, scale **`spend` and `rec_extra` only**.
- Do **not** touch housing, wellness, LTC, lumps or business expenses.
- Both `total_spend` assembly sites (`:1405`, `:1565`) must agree.

**Tests** (`tests/test_survivor_spending_regression.py`, new):
- Survivor-year `spend_base_yr` is 0.65 × the both-alive figure; the both-alive years are unmoved.
- `housing_total_yr` and `wellness_base_yr` are **unchanged** by the factor — the double-count guard.
- A factor of 1.0 reproduces today's numbers bit-identically.
- Demonstrate RED before implementing.

## Task S2 — post-second-death rows are estate-only

**Model · effort: opus · medium.** Latent today, so tests must construct the condition explicitly.

- When `n_alive == 0`, every living-expense component of `total_spend_need` is zero: core,
  `rec_extra`, lumps, housing (all of it), rent, wellness, LTC, business expenses, HELOC P&I.
- Taxes on estate income and any liability servicing that genuinely survives death may remain —
  state which and why in the report.
- `unfunded_gap` must be structurally impossible once nobody is alive.

**Tests** (same file):
- With `plan_end` extended past the second death, all living-expense components are 0 and
  `unfunded_gap` is 0 for every post-death year.
- A default-horizon plan is **bit-identical** — this task must move nothing today.

## Task S3 — home sale at second death

**Model · effort: opus · high.** Touches asset disposition and basis.

- At the second death, dispose of the home through the **existing** home-sale machinery
  (`home_sale_net`/`home_sale_costs`/`home_sale_gain`/`home_sale_tax`). Do not build new mechanics.
- Apply the existing second-death step-up so the taxable gain is right.
- Carrying costs stop from the sale year.

**Tests** (same file): post-death `home_val` goes to 0 and proceeds appear in the estate; carrying
costs are 0; gain reflects the step-up.

## Downstream gates S4 must also handle (found during S1-S3 implementation)

Two suites beyond the two named pins moved when S1-S3 landed. Neither indicates a defect in
this plan's work — both are documented as fragile-by-design in their own source, and this
plan's change is a substantial, deliberate engine change, not noise.

1. **`tests/test_synthetic_golden_master.py`** — 9 of 10 scenarios move, all upward (found
   during S1; see S1's task section). A second golden-master-shaped gate the original plan
   did not name. Must be regenerated alongside the two named pins.

2. **`tests/test_withdrawal_sequencing_comparison_regression.py::test_current_plan_is_the_lowest_tax_and_highest_terminal_of_the_four`** — the `proportional` strategy now edges out
   `current_plan` on terminal NW by ~0.88% (1,486,978.06 vs 1,473,968.52); the lifetime-tax
   half of the assertion still holds. **The test's own docstring for `sample_config_and_rows`
   already warns**: *"The strategies here are ranked against each other by margins well under
   a percent, so a stale quote flips them."* Confirmed against origin/main with this branch's
   changes stashed: the comparison passes cleanly on the unmodified engine, so S1-S3 genuinely
   closed an already-thin margin rather than exposing a pre-existing flake. Left untouched —
   fixing the withdrawal-sequencing engine itself is out of scope for a spending/mortality
   change and risks a blind edit to code this plan does not own. S4 (or a human) must decide:
   accept the new ranking and adjust the test's threshold/expectation, or treat it as a real
   finding about the current-plan sequencing under reduced survivor spending.

## Task S4 — regenerate and document

**Model · effort: opus · medium.**

- Regenerate `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` via the test file's `__main__` block.
- `GOLDEN_MASTER_CHANGELOG.md` entry stating the movement, its **direction** (upward), its cause
  (survivor spending 1.00 → 0.65), and that S2/S3 contribute nothing on a default horizon.
- Report the before/after pins and the delta explicitly.
