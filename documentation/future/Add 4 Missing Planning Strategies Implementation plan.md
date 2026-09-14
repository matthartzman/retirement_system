# Add 4 Missing Planning Strategies: 72(t)/SEPP, Backdoor/Mega-Backdoor Roth, NUA, CRT

## Context

A codebase survey found the system already implements a broad set of tax/estate optimization strategies (Roth conversion bracket-fill, TLH, gain harvesting, asset location, QCD/DAF, AMT, RMD, step-up basis, estate portability, gifting, 529s, equity comp). Four commonly-used real-world levers are absent entirely: **72(t)/SEPP** (penalty-avoidance for early pre-59½ withdrawals), **backdoor/mega-backdoor Roth** (high-earner Roth access), **NUA** (net unrealized appreciation on employer stock held in a 401(k)), and **CRT** (charitable remainder trusts, for large appreciated/concentrated positions — QCD/DAF don't substitute for this). This plan adds all four as new optional modules following the codebase's existing module pattern, so they compute, report, and gate on/off identically to modules like `gain_harvest.py`.

## Architecture pattern (confirmed via exploration, reused for all 4 modules)

Every optional module follows the same shape, using `gain_harvest.py` as the template:
1. **Pure logic file** `src/<module>.py` — one or two pure functions: a selection/eligibility function and a scan/reporting function that builds the ledger. No side effects, no I/O.
2. **Engine wiring** in `src/deterministic_engine.py` — gate on a policy flag (`c.get('<module>_policy')=='apply'`), call the module function inside the year loop, store results on `row['<module>_...']`.
3. **Inputs** sourced from `data_io.parse_client` — new policy knobs read via the existing `_sv(...)` pattern from `client_policy.csv`; any new per-client facts (e.g., employer stock lots, cost basis) from `client_holdings.csv`/`security_master.csv` if reusable, else a new CSV section.
4. **Catalog entry** in `src/module_catalog.py` — append an `OutputModule(...)` to `_OUTPUTS` (kind=`optimization`) + a `SHEET_REGISTRY` row if it owns a sheet. This auto-wires compute-skip, sheet drop, and nav/PDF gating via `module_enabled()`/`OPTIONAL_MODULE_SHEETS`/`step_gate_map()`.
5. **Toggle** row added to `client_optional_functions.csv` (and fixture/demo copies) keyed by the new module key.
6. **Reporting** function `build_sheet_<module>(ws, c, rows)` in `src/reporting/sheets_strategy.py`, called from `workbook_builder.py` gated by `module_enabled(c, key)`.
7. **Tests**: unit test mirroring `tests/test_gain_harvest_zero_bracket.py` (build config, override policy, assert dict) + an off-by-default no-op test (`baseline_config_without_*_overrides`) + extend `tests/test_optional_module_gating.py` for on/off sheet-presence.

Closest tax-mechanics analogs to reuse patterns from:
- `src/core.py:942-970` (QCD) — statutory dollar cap + age-eligibility gate → template for 72(t)/SEPP limits and Roth contribution-limit gating.
- `src/core.py:973-1028` (AMT) — asymmetric basis split + credit carryforward → template for NUA's ordinary-vs-LTCG basis split.
- `src/after_tax.py:298-345` (step-up basis) — classify-into-case → fraction → explanatory note pattern → template for NUA's basis/appreciation split and CRT's remainder-interest valuation.

## Module-by-module plan

### 1. Backdoor / Mega-Backdoor Roth (`src/backdoor_roth.py`) — build first (simplest, no new schema)
- Logic: given MAGI vs. Roth IRA phase-out thresholds (already have tax-bracket infra in `taxes.py`) and existing 401(k) contribution room, compute (a) nondeductible traditional IRA contribution + immediate conversion amount, respecting pro-rata rule if client has existing pre-tax IRA basis, and (b) after-tax 401(k) contribution room (employer plan limit minus employee/employer contributions already modeled) eligible for in-plan Roth conversion.
- New policy knobs: `backdoor_roth_policy`, `mega_backdoor_roth_policy` in `client_policy.csv`.
- Engine: wire into the same conversion year-loop section as existing Roth conversion logic in `planning_engines.py` (~1254-1660) — this is additive room, not a competing conversion policy.
- Sheet: new sub-section on existing Roth conversion sheet, or new `OutputModule` `backdoor_roth` (kind=optimization).

### 2. 72(t)/SEPP (`src/sepp.py`)
- Logic: given an account balance, life expectancy tables (reuse RMD's existing life-expectancy table source if present — check `src/core.py` RMD section), and account holder age, compute SEPP payment under the three permitted methods (RMD, fixed amortization, fixed annuitization) and flag the 5-year/age-59½ modification lock-in. Emits a penalty-avoidance schedule and a "broken SEPP" penalty-recapture warning if a scenario's withdrawal deviates.
- Relevant only pre-59½: gate on `age < 59.5` at scenario start, similar to QCD's `qcd_eligible_from_year` age-gate pattern.
- New policy knob: `sepp_policy`, `sepp_method` (rmd/amortization/annuitization).
- Engine: wire into `deterministic_engine.py` withdrawal-sequencing section — SEPP is a withdrawal-source constraint, not a conversion.
- Sheet: new `OutputModule` `sepp_planning`.

### 3. NUA (`src/nua.py`)
- Logic: given employer stock lots inside a 401(k) (cost basis vs. current value — reuse `c['lots_by_account']`/`security_master.csv` lot structure already used by `gain_harvest.py`/`tlh.py`), compute the in-kind-distribution split: ordinary income on cost basis at distribution (taxed like any 401(k) distribution) vs. LTCG treatment on the NUA amount when later sold, vs. the baseline (roll everything to IRA, all-ordinary-on-distribution). Output a break-even/recommendation similar to `daf_optimizer.py`'s recommendation shape.
- Requires employer-stock lots to be flagged as such — check if `security_master.csv` already has an issuer/employer-stock flag; if not, add one optional column (backward-compatible, defaults to false).
- New policy knob: `nua_policy`.
- Engine: one-time event, likely evaluated at retirement/separation-from-service year, not per-year — closer to `equity_comp.py`'s event-based structure than the year-loop modules. Investigate `src/equity_comp.py` wiring as secondary template before implementation.
- Sheet: new `OutputModule` `nua_analysis`.

### 4. Charitable Remainder Trust (`src/crt.py`) — build last (most novel, reuse least code)
- Logic: given a client-selected appreciated/concentrated taxable-account position (reuse taxable lot structure), CRT term (life or term-of-years), payout rate (%), and §7520 rate, compute: (a) IRS-approved charitable deduction (present value of remainder interest — standard actuarial CRT formula), (b) deferred capital gains avoidance vs. selling outright, (c) projected income stream to grantor taxed under CRT four-tier accounting (ordinary/capital gain/other/corpus), (d) remainder to charity at term end. This is net-new actuarial math not present elsewhere in the codebase — no direct analog beyond the step-up "classify→fraction→note" shape for the remainder-interest valuation.
- New client inputs: selected position(s), CRT type (CRAT/CRUT), term, payout rate — new CSV section `client_crt_elections.csv` or extend `client_policy.csv` if scope stays single-trust-per-client.
- New policy knob: `crt_policy`.
- Engine: one-time election evaluated in the same pass as DAF/QCD (`daf_optimizer.py` is the closer structural template than gain_harvest.py here, since it's also a charitable-giving lever with an "AGI limitation and carryforward" concern — see `tests/test_daf_agi_limitation_and_carryforward.py`).
- Sheet: new `OutputModule` `crt_planning`, positioned near the existing Charitable Giving module in the catalog.

## Execution plan: model/effort tiering per phase

Goal: match model effort to where correctness risk actually lives (tax/actuarial math) vs. where it's mechanical repetition (scaffolding), to control token spend without sacrificing quality on the parts that matter.

| Phase | Work | Agent/Model | Effort |
|---|---|---|---|
| 1 | Backdoor Roth: logic + wiring + tests | Sonnet | medium |
| 2 | 72(t)/SEPP: logic + wiring + tests | Sonnet | medium-high (statutory penalty rules — getting this wrong has real IRS-penalty stakes) |
| 3 | NUA: logic + wiring + tests | Sonnet | high (basis/LTCG split math, one-time-event wiring is a new pattern) |
| 4 | CRT: actuarial logic + wiring + tests | Sonnet | high (net-new actuarial formulas, no in-repo template) |
| 5 | Catalog/toggle/CSV plumbing for all 4 (module_catalog.py entries, SHEET_REGISTRY, client_optional_functions.csv, fixture copies) | Sonnet | low — mechanical, closely copies existing entries |
| 6 | Reporting sheets (sheets_strategy.py functions, workbook_builder.py gating) for all 4 | Sonnet | low-medium — closely copies `build_sheet_gain_harvest` shape |
| 7 | Cross-module review pass (tax correctness, golden-master regression check, gating cycle validation via `module_catalog.validate()`) | Sonnet | high, single consolidated pass at the end rather than per-module review |

Sequencing rationale: build in increasing order of novelty (backdoor Roth → SEPP → NUA → CRT) so each phase can crib patterns from the previous one, then batch all the low-effort plumbing/reporting work together at the end since it's near-identical across all 4 modules (avoids re-deriving the module_catalog/CSV/sheet pattern 4 separate times). One consolidated high-effort review at the end catches cross-module issues (e.g., a client eligible for both SEPP and backdoor Roth in the same year) more cheaply than 4 separate review passes.

Do the actual implementation via the `claude` agent type (general-purpose) with `model: sonnet` and explicit effort framing in each prompt (since this harness doesn't expose an "effort" knob directly on Agent calls — effort is achieved by how much investigation/validation each prompt asks for, and by using a dedicated review pass for the high-stakes phases rather than a higher-tier model).

## Verification

- Per module: run its new unit test file directly (`pytest tests/test_<module>.py -v`) with `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` set (per existing convention in `conftest.py`).
- After each phase: run `pytest tests/test_optional_module_gating.py tests/test_all_modules_off_build_functional.py -v` to confirm on/off gating doesn't break existing modules.
- After all 4: run the full test suite once, and check `git status` on `input/` afterward per known issue that some tests mutate input fixtures (memory: pytest mutates input files) — do not commit any incidental fixture drift without review.
- Full golden-master regression run at the end of phase 7 to confirm no `_mode` column or terminal-net-worth drift on scenarios that don't opt into the 4 new modules (should be exactly zero diff, since all are `optional=True` and off by default).
- Manual spot-check: enable each module for one test client via `client_optional_functions.csv`, rebuild the workbook, confirm the new sheet appears with correct nav/PDF gating and disappears when toggled off.
