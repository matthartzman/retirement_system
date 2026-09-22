# W9 — UI section registry: what was built, and the judgment calls

> Execution record for **W9** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4, implementing #329 P4 + #330. Requires W3, W6 — both landed on this branch.

## Scope, as the plan states it

> Scope: `strategySection()` registry edits to match #329 §3.3's UI list;
> restore Withdrawal Sequencing, Asset Location and Scenario Analysis (each
> its own tab); move HELOC to Assets & Protection; add Divorce/QDRO's
> workbook sheet; `navigation.js` redirects.
> **Cost driver:** the redirects are the fiddly part, not the registry.

## Triage of the five items PR #132 handed W9

PR #132's "What's left on the master plan" section named five inherited
items and explicitly asked this workstream to triage them against its own
scope rather than silently doing all five or dropping them. The call:

| Item | Call | Reasoning |
| --- | --- | --- |
| `rowsForStep()`'s hand-written HELOC gate (`dashboard_decomp_row_model.js`) | **IN SCOPE** | Directly entangled with "move HELOC to Assets & Protection" — touching HELOC's page context makes this a few-line generalization to read `flag_gates` like the two branches W6 already converted, not a new task. |
| Plan Features link rows for plan flags (HELOC, Hybrid LTC, DAF, QCD) | **IN SCOPE** | W6's own notes assign this here explicitly: "Adding the link rows is a UI change, not a refactor, and belongs with W9's UI section registry." `gate_ref`/`gate_enable_label` already carry everything a link row needs. |
| A real "any of these gates" bundle declaration, if `special_strategies`-style steps come back | **OUT — no consumer** | Nothing in #329 §3.3's UI list revives a bundle-gated step. W6 deliberately did not invent this field for a hypothetical; W9 doesn't create the hypothetical either. Stays deferred. |
| Hide the YTD tab within `spending_core` when Spending Tracker/YTD is off | **OUT — belongs to W12** | This is a `rowsForStep`/tab-visibility change matching W12's own scope line verbatim: "implement the three off-states (Hidden/Collapsed-with-note/Disabled-in-place) chosen from declared data." Building one more hand-written tab-hide here pre-empts the generalization W12 exists to do, the same over-building W6 itself cut back on its first Hybrid LTC pass. |
| Hybrid LTC soft dependency (`long_term_care_stress` → `degrades_without`) | **OUT — needs new plumbing, not a link row** | W8b's notes are explicit: satisfying it needs a *new catalog field* mapping `gate_ref` to its parsed config key, plus a parallel sweep test for plan-flag reads (today's sweep only recognizes module-toggle read spellings). That is W5-shaped dependency-declaration work, not UI registry work, and building it minimally here risks exactly the aspirational-declaration trap `test_every_soft_declaration_is_backed_by_a_swept_call_site` exists to catch. Deferred to whichever workstream next touches `degrades_without`. |
| Housing Location Search catalog entry (`src/housing/`, "Where to live") | **OUT — W1-shaped, per the task brief itself** | Confirmed against W8b's own notes: no `CATALOG` entry exists, and making one optional is a catalog addition plus UI-panel gating, not a toggle row. Not touched. |

## What "restore ... each its own tab" means

`_hidden()` vs `_visible()` (W3) is a **workbook nav** distinction — a hidden
sheet is still built and gated normally, just absent from the lettered tab
strip. All three of Withdrawal Sequencing (`retirement_strategy`), Asset
Location (`asset_location`) and Scenario Analysis (`what_if_analysis`)
already carry `optional=True`, an existing `module_key`, and an existing
`TRUE`-defaulted toggle row in `input/demo/client_optional_functions.csv` —
this is a pure nav-visibility change, not a gating change. Confirmed none of
the three collide with `test_every_optional_module_has_a_toggle_row` or the
build-gating tests before starting.

Note the master plan's phrase names three *workbook* restorations. Only two
of the three also get a **UI** panel per #329 §3.3's own final list ("Roth
Conversion · HSA Drawdown · Asset Allocation · Withdrawal Sequencing · Social
Security · Next Housing Move · Charitable Giving · Harvesting") — Asset
Location is not in that list and stays workbook-only, exactly as the spec's
§3.3 table has it (only Asset *Allocation* appears there, unchanged).
