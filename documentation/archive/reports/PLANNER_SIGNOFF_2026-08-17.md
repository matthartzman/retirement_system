# Planner sign-off — Wave 3.8 / F4 · 2026-08-17

**Closes:** `REMAINING_WORK_PLAN_2026-08-12.md` **F4.1, F4.2, F4.3**, and `SYSTEM_REVIEW_2026-08-04.md`
Wave **3.8** and its three remaining open questions (§6).

**Supersedes:** the manual stand-in sign-off in `SYSTEM_REVIEW_2026-08-04.md` §7, which was taken on
2026-08-05 under a session-limit block and predates every engine change it was meant to review.

**Basis:** source-level re-derivation of the Wave 3 engine work as it actually stands at
`wt/js-split` (`d205973` + F3.4 working tree), plus two purpose-written measurement scripts against
the frozen fixture. Gate evidence: `test_frozen_sample_plan_golden_master_regression.py` and
`test_monte_carlo_per_account_returns_wave35.py`, **10 passed**, pins 5,824,239.30 / 1,290,848.91,
`input/` clean afterwards.

---

## Verdict

**Signed off, with one disclosure required and one follow-up tracked.**

Wave 3's engine items are present and behave as claimed in the deterministic path. The Monte Carlo
per-account work (3.5 / F1) is **materially complete but is not the model the plan specified**, and
the substitution was never recorded. It is a defensible engineering choice; it is not a defensible
*silent* one, because it changes what the headline success rate can and cannot support.

Nothing here blocks F3, F5, or a client-facing build. Finding **S2** should be disclosed in the
Monte Carlo methodology note before the next client deliverable.

---

## 1. F4.1 — Sign-off on the finished engine work

### Method, and why it differs from the last one

The 2026-08-05 stand-in reviewed the *plan document*. This one reviews the *code*, because the
record has now been wrong three times in a row about this exact item (see §3). Every claim below was
re-derived from source or measured; nothing was accepted from a commit message.

That was the right call. The commit that landed F1 (`8522862`) describes work that did not function:
it wrote **absolute** per-account rates onto a path that already carried its own sampled return
(compounding a 4.98% IRA at ~10.5%), and it left the **vectorized** path — the one that produces the
headline success rate — untouched. Both defects were caught and fixed afterwards in `1bbae33`. The
current implementation is the one reviewed here, not the one the plan's status table describes.

### What the engine actually does now

Per-account returns reach Monte Carlo as a **constant mean shift**, not as sleeve-level draws:

- `_account_return_tilt()` (`src/planning_engines.py:66`) converts each account's absolute CMA return
  into a **tilt** relative to the plan return — the correct unit for a path that already sampled its
  own return.
- The scalar/loop MC path applies tilts per account (`_apply_account_return_adjustments`, `:143`).
- The **vectorized** path collapses tilts to the four tax buckets by dollar weight
  (`_mc_bucket_return_tilts`, `:93`) and adds each bucket's constant to the shared sampled return
  (`_mc_apply_bucket_growth`, `:130`; applied at `:3217`).
- Cash is excluded from tilting and grown on a short-rate proxy tied to inflation (`:3219`) — sound,
  and better than tilting it against an equity draw.

### S1 — The delivered model is a mean shift; the plan specified a variance model

F1.1 specified: *"Replace the MC weight **vector** with a weight **matrix** (`raw.dot(W)`,
`W` = n_classes × n_sleeves) and route each account to its sleeve column."* What landed keeps
`raw.dot(wv)` (`:3013`) — still a vector — and adds a per-bucket constant afterwards.

The practical difference is **variance, not mean**. Under a weight matrix each sleeve draws its own
correlated return, so a bond/cash sleeve is genuinely less volatile than an equity sleeve. Under a
constant tilt, **every bucket takes the identical shock** and differs only by a fixed offset.

Consequences a planner should hold onto:

- Asset **location** (which account holds what) is now modeled, directionally. This satisfies the
  letter of finding C3.
- Asset **allocation de-risking inside the four market buckets** is invisible. A bond tent or
  glidepath held within taxable/pretax/Roth/HSA produces **no sequence-of-returns protection** in the
  success rate, because those bonds take the identical annual shock as equities, merely offset by a
  constant.
- Therefore: **do not ship any recommendation whose justification is that de-risking inside
  retirement accounts reduces failure risk, and cite the MC success rate as evidence.** The engine
  cannot see that effect. Recommendations resting on asset *location* are supported.

> **Correction (2026-08-17, during P4).** This finding as first written said "a cash reserve, a bond
> tent, or any bucket strategy" produces no protection. **The cash half was wrong.** The vectorized
> path grows the `cash` bucket on a short-rate proxy tied to inflation rather than the equity draw
> (`planning_engines.py:3219`), so a cash reserve held in a cash-type account genuinely *is* modeled
> as low-volatility. The gap is narrower than stated and confined to the four market buckets. Found by
> reading the built Sheet 3A output while writing P4's disclosure, not by re-reading the source —
> which is the same lesson §3 rule 1 draws, applied to this document's own claim. The commit message
> on `399d093` carries the original overstatement; this section supersedes it.

This is a reasonable scope reduction — a full sleeve covariance structure is a much larger change
than F1's "M · 1–2 days" estimate allowed. The defect is that no document says the substitution
happened, so the plan, the changelog and project memory all still describe a weight matrix.

### S2 — The "market-neutral" tilt is not neutral, and drifts +20 bps in the plan's favor

`_account_return_tilt`'s docstring claims tilts are *"dollar-weighted to approximately zero across
the portfolio by construction, so applying them preserves the plan's expected return."* That holds
for the raw tilt set at t=0. It does **not** hold for what the MC actually applies, for two reasons:

1. `_mc_bucket_return_tilts` re-weights by **projection balances**, while the tilts were built from
   **holdings market values** (`src/data_io.py:2443`), and it drops cash-tax and zero-balance
   accounts. Neutrality is never re-established after the filtering.
2. More importantly, the four bucket constants are computed **once at t=0** and applied to **every
   year** — while the projection deliberately reshapes the bucket mix underneath them.

Measured on the frozen fixture (`scratchpad/measure_tilt_drift.py`, deterministic bucket balances,
tilts as the vectorized MC applies them):

| Year | Portfolio | Effective portfolio-wide tilt |
|---|---:|---:|
| 2026 | 2,956,625 | +4.3 bps |
| 2036 | 3,192,809 | +7.6 bps |
| 2046 | 3,076,494 | +15.0 bps |
| 2056 | 1,458,598 | **+24.9 bps** |

Bucket constants on this fixture: `hsa +30.2 bps · roth +24.9 bps · taxable +13.3 bps ·
pretax −5.4 bps`. On the account-balance basis the t=0 net is +2.8 bps.

The drift is **monotonic, upward, and structural**. Withdrawal sequencing and RMDs drain the
negatively-tilted pretax bucket, and Roth conversions actively move dollars from the −5.4 bps bucket
into the +24.9 bps one. So the effective return assumption rises through exactly the late years where
Monte Carlo success or failure is decided.

**The sharp version, and the reason this is a planner finding rather than a code nit:** every dollar
the engine recommends converting to Roth is thereafter assumed to earn ~30 bps more, forever. That
is not because converted dollars buy different assets — they arrive as cash and would be invested per
the target allocation — but because they inherit the Roth account's *current* holdings tilt. The Roth
conversion analysis then ranks strategies by success rate. **A core recommendation of this system is
scored with a small tailwind it creates for itself.**

Magnitude is modest — roughly 20 bps on a 5% assumption, in the terminal decade. This is a
disclosure-and-fix item, not a stop-ship. But the direction is not random, it favors the
recommendation, and it is currently invisible to every reader.

### S3 — The test guarding S2 asserts a property it never checks

`test_bucket_return_tilts_are_dollar_weighted_and_market_neutral` (F1.2) tests dollar-weighting
correctly and **does not test market neutrality at all**. Its own fixture is nowhere near neutral
(bucket tilts of +373 bps and +200 bps), contains no cash account, and the word "neutral" appears
only in the name. The name is load-bearing: it is why S2 reads as covered.

This is the same shape as the three defects `4b6c818` found in F2's tooling and the
`find_dead_functions.mjs` defect fixed in `3979d17` — **a check that reports success without doing
its job** — now at four instances in this codebase within a fortnight. See §3.

### S4 — F1.2's acceptance criterion cannot detect S1

The criterion was *"assert MC per-account terminal balances diverge across sleeves."* A constant tilt
makes balances diverge. So the test passes identically whether the engine implements the specified
weight matrix or the delivered mean shift — it cannot distinguish the two, which is the one
distinction that mattered. Divergence was the wrong observable; **differential variance** was the
right one.

### S5 — Minor: the two MC paths disagree about cash (no impact today)

The vectorized path excludes cash-tax accounts from tilting and grows them on the short-rate proxy.
The scalar/loop path (`_apply_account_return_adjustments`) applies a tilt to any account present in
`account_returns`, cash-tax or not. On the frozen fixture the cash accounts hold no
CMA-classifiable securities, so they are absent from `account_returns` and the paths agree. A plan
holding a money-market fund that maps to a CMA class in a cash account would make them disagree.
Low severity, worth one line in the follow-up.

### Wave 3 items other than 3.5

3.1–3.4, 3.6, 3.7 were verified as present and the golden gate is green at the current pins with
`input/` unmutated.

The pre-flight condition attached in §7.4 of the review — *resolve or triage the 18
`pytest -m "not slow"` failures before 3.0* — is **satisfied, independently re-measured 2026-08-17**
during the P1 verification below: fast tier **1,635 passed, 4 skipped, zero failures or errors**,
`input/` unmutated. This supersedes the first draft of this section, which cited `4b6c818`'s commit
message and correctly flagged that as a read rather than a verification (§3, rule 1). Note the run
includes F3.4's uncommitted extraction, so it is evidence for that tree state, not for `d205973`
alone; F3.4 still owes its own full-suite run.

---

## 2. F4.2 — The review's three remaining open questions, closed

**Q1 · Verifier adversariality (C1, C2, C5, C6 never got a source-level second look).**
**Closed as: confirmed defect, rule written.** No longer an open question — it is now a settled
finding with four instances. C6 (Playwright) was overtaken by events as §7.4 recorded: it was built,
and it caught a real bug on its first substantive spec. C1, C2 and C5 remain un-re-assessed, and on
the evidence in §3 that is a real residual risk rather than an academic one. Disposition: rather than
re-audit three findings individually, the standing rule in §3 changes how *all* future verification
is done, which is the higher-leverage fix. Re-assessing C1/C2/C5 is logged as an optional follow-up,
not a blocker.

**Q2 · Wave 5 has no sequencing rationale.**
**Closed as moot.** All six Wave 5 items shipped (Sheets 15/37, sustainable-spending solve, LTC, life
insurance) without a sequencing problem materializing. The hypothesis that 5.1 and 5.5 shared
machinery was never tested and no longer can be usefully. No action.

**Q3 · XL items have no decomposition.**
**Closed as moot — and the concern was validated in practice.** 2.1, 4.x and 6.4 were each decomposed
before execution: 2.1 into per-journey Playwright specs, 6.4 into the cluster-by-cluster split now at
F3.4. 6.4 in particular vindicates the question — it ran to eleven-plus sessions against an "XL /
2+ weeks" estimate, and it only became tractable once F2's tooling made per-cluster passes cheap.
The lesson worth carrying forward: **the XL estimate was not wrong about size, it was wrong about
shape** — the cost was in test breakage per pass, not in the extraction, and no amount of up-front
decomposition would have surfaced that. Measuring one pass did.

---

## 3. F4.3 — Verifier adversariality, re-opened and ruled on

The review recorded a **0/28 refutation rate** across its cross-check stage and flagged it as
suspicious. That suspicion is now confirmed. Documented misses, in order:

| # | What was verified | What the verifier missed |
|---|---|---|
| 1 | C4, mortality tables | A **second, vectorized mortality sampler** — the one producing the headline success rate (review §2.5) |
| 2 | The frozen golden-master pin | The pin never described the fixture; every measurement had been taken in one environment (plan §2) |
| 3 | F2.1/F2.2/F2.3 tooling | All three shipped non-functional: a `--check` that returned success without executing, a guard that could not fail, a sweep whose imports landed but whose reads did not (`4b6c818`) |
| 4 | F1, per-account MC returns | Wrong units, and the headline path untouched (`1bbae33`); then **S1–S4 above** |

**The common shape is not carelessness. Every one of these was a confirmation of a prior conclusion
rather than an independent re-derivation.** In each case a green signal existed — a passing test, a
prior bisect, a commit message, a docstring — and verification consisted of observing that the signal
was still green. A verifier that agrees with the record has not verified the record; it has read it.

Note that instances 3 and 4 are *self-referential*: the mechanisms built to catch this class were
themselves shipped broken and passed their own review. That is what makes this worth a standing rule
rather than a note.

### The rule

> **A green check is evidence only if you have seen it go red.**
>
> 1. **Verification must re-derive, not re-read.** If a check's output can be predicted from the
>    record without opening the artifact, it is not verification. State what was independently
>    measured and how.
> 2. **Every new guard, gate, or acceptance test must be demonstrated failing** on a planted
>    violation before it is trusted, and the demonstration recorded in the commit. "Passes on a clean
>    tree" is compatible with a guard that cannot fail — which is how all four instances above
>    survived.
> 3. **Assert on the observable that distinguishes the hypotheses.** S4 is the pattern: the test
>    asserted divergence when only differential variance separated the delivered model from the
>    specified one. Before writing an acceptance test, name the wrong implementation it must reject.
> 4. **A test's name is a claim; audit it against its body.** S3 shipped a neutrality assertion that
>    exists only in the identifier.
> 5. **When a measurement depends on the environment, take it in two environments.** Instance 2 cost
>    the most and would have been caught by this alone.
> 6. **Refutation rates near zero are a defect signal, not a quality signal.** Treat any verification
>    sweep returning >90% confirmations as unverified until spot-checked adversarially.

Rules 2 and 5 have already paid for themselves once each — `4b6c818` adopted rule 2 for the rewritten
direct-read guard (planting a real violation, confirming it went red naming file and line), and rule 5
is what broke open the frozen-gate diagnosis.

---

## 4. Follow-ups this sign-off creates

None are blockers. Ordered by value.

| # | Item | Effort | Suggested |
|---|---|---|---|
| ✅ P1 | **Re-normalize the bucket tilts every step.** **DONE 2026-08-17** — `_mc_apply_bucket_growth` now subtracts the current step's balance-weighted mean tilt, so neutrality holds at every year and on every path independently rather than only at t=0. Realized portfolio growth now equals the sampled return to floating point in every projection year (worst excess **0.000000 bps**, was +24.9). The inter-bucket spread — the Wave 3.5 deliverable — is preserved exactly. Golden pins unmoved; changelog entry 2026-08-17. | S | opus · medium |
| ✅ P2 | **Regression guard.** **DONE 2026-08-17** — `tests/test_mc_bucket_tilt_neutrality_regression.py`, six cases. Per rule 2 it was demonstrated red first: the all-Roth end-state case failed by **+24.87 bps**, matching the fixture measurement that motivated it. Covers the late-horizon mix, per-path independence, the degenerate single-bucket end state, preservation of the spread (so a fix cannot degenerate into zeroing the tilts), and the untilted bit-identical path. | S | sonnet · medium |
| ✅ P3 | **DONE 2026-08-17.** Renamed to `test_bucket_return_tilts_are_dollar_weighted`, with a scope note in the docstring recording that the neutrality claim existed only in the identifier (S3) and pointing at P2's file as the place it is actually asserted. The cross-reference in that file was updated to match. Body unchanged. | XS | sonnet · low |
| ✅ P4 | **DONE 2026-08-17.** Two rows added to Sheet 3A (Monte Carlo) section A, directly above the success rate: what asset location does model, and the limit on what the number supports. Guarded by `test_monte_carlo_sheet_discloses_the_asset_location_modeling_limit`, demonstrated red first against a real build, resolving the sheet through `stable_name_for_sheet_title` rather than a hardcoded `3A.` (section letters are recomputed per build). Recorded here, in the plan, in the changelog and in project memory. Writing it corrected S1 — see the banner above. | S | sonnet · medium |
| ✅ **P7** | **DONE 2026-08-17.** Re-worded to rest on what is modeled (option 1). Section G's *Primary Risk* item now names withdrawal ORDER as the credited mitigation — the cascade spends cash-type accounts first and cash grows on a short-rate path — and states plainly that the configured buffer is a different mechanism that sets a floor under the taxable/Trust draw while every reserved dollar still takes the full bucket shock, and that the floor is applied only in the deterministic cascade, never re-enforced per simulated path. **Option 2 was found to be unavailable:** a Liquidity Buffer row's `reserve_account` field is written and round-tripped by the UI and read by nothing in the engine — the floor hits the taxable bucket whatever it says — so selecting "Cash" there cannot make the claim true. Only holding the reserve in a registry account with `tax='cash'` does. That inert field is logged as P8. Scope note: **section E's quintile note carried the same claim more strongly** ("riding out early bear markets without forced selling" — the model has no forced-selling mechanic at all) and was fixed in the same pass; leaving it would have had the sheet contradict itself. Audit of G's other five items: three are computed values, two are review triggers, none make an S1-class claim — they stand. Guard: `test_monte_carlo_sheet_does_not_credit_the_liquidity_buffer_with_mitigating_sequence_risk`, each of its three assertions demonstrated red individually against a real build (per §3 rule 2, including the positive assertion — a forbid-only guard passes on a sheet that says nothing). Also checked what these guards structurally cannot see: they read cell *values*, so a disclosure could be present and still be visually clipped. Measured the rendered geometry of all three passages (this one, the section E note, and P4's) in a built workbook against `minimize_row_heights`' calibrated width model at the final column widths — 5/3/6 lines needing 73/45/87 pt against 73/45/87 pt allotted. Nothing is clipped; recorded because the check is not obvious from the test names. | S | opus · medium — it is client-facing advice, not description |
| ✅ P5 | **DONE 2026-08-17.** `_apply_account_return_adjustments` now applies the same cash-tax exclusion as `_mc_bucket_return_tilts`, so the scalar path stops tilting cash accounts against an equity return the vectorized path never applies to them. Guard: `tests/test_mc_cash_tilt_path_parity_regression.py`, built on the exact fixture S5 named (a money-market fund mapping to a CMA class, held in a cash account) since the frozen fixture cannot distinguish the two implementations — per §3 rule 3. Demonstrated red on the pre-fix engine. Golden pins unmoved. | XS | sonnet · low |
| ✅ **P8** | **DONE 2026-08-17 — honored, not removed.** `liquidity_buffer_for_year` now returns `(years, bucket)` and a new `liquidity_reserve_floor(c, year, bucket, spend_floor_base)` applies the floor to the bucket the row names, in `withdraw_taxable_trust`, `withdraw_roth`, `withdraw_pretax_elective` and `withdraw_hsa_gap`, with `spend_floor_base` threaded through all six deterministic call sites. Two consequences beyond the floor, both deliberate: `trust_surf` no longer subtracts a non-taxable reserve from the taxable balance (it was understating Roth-conversion capacity), and an IRA reserve now caps conversions too — converting empties the reserved bucket as surely as spending it. **Cash is a documented no-op**: the deterministic cascade never draws cash-tax accounts, so a cash reserve is preserved by construction; the floor helper still returns the right number and `CashReserveTests` pins it for whoever adds a cash draw. **Golden pins unmoved by design** — the default, unrecognized and blank values all resolve to taxable, so every stored plan is bit-identical. Guard: `tests/test_liquidity_reserve_account_regression.py`, 12 cases; planting the pre-P8 taxable-only semantics turned 7 red, and the 5 that held are the pins that must be insensitive. | S | opus · medium — silent no-op on a client-visible input |
| ✅ P6 | **DONE 2026-08-17 — and it found one.** Source-level second look at C1, C2, C5 under the §3 rule. **C1 and C5's engine fixes are real** and were re-derived, not re-read. **C5's guard was not:** `test_terminal_component_is_discounted_below_nominal_after_tax_nw` computed the present value itself and asserted `pv < nominal` — true by arithmetic for any positive discount over any positive horizon — while never reading the objective. Demonstrated: with `after_tax_terminal_nw_pv` reverted to the nominal figure (C5's defect, fully restored) **both tests stayed green**. Rewritten to assert on `terminal_wealth_score`, the component that actually enters the score; the planted defect now fails it by 6,185,244 vs 2,948,770 — the objective had been weighting terminal wealth at **2.1×** its present value against discounted tax terms. Two C2-class residuals logged as P9. Full detail in §5. | M | opus · high |

| ✅ **P9** | **DONE 2026-08-17.** All four figures on `19. Life Insurance` now derive from the plan: the hybrid verdict from `ltc_face`/`ltc_start_year`/`ltc_annual_prem` (it previously printed “$500K face, start 2027, ~$18,500/yr” in the same row whose Death Benefit column renders the configured face), the GUL verdict from `summary_figures.credit_shelter_trust_savings` instead of a flat $320K, and the Estate Liquidity Buffer from `estimate_terminal_estate_tax` instead of a flat $500,000 — that one sat one row under Section B’s own note boasting these needs are not a generic multiple. Also removed a named commercial product from the closing recommendation, labeled the premium table as indicative pricing rather than quotes, and revived a **dead `is_optimal`**: it computed which coverage row matched the client’s configured face and was discarded in favor of a ★ baked into the $500K string, so every client saw $500K as “OPTIMAL”. Guard: `test_insurance_sheet_prints_no_client_independent_dollar_figures`; all seven assertions demonstrated red against a real pre-fix build. Reporting only — no projection figure moves. | S | sonnet · medium |

**P4 is the one with a client-facing deadline** — it is a disclosure, and the next build ships without
it otherwise.

---

## 5. P6 — the second look at C1, C2, C5

Run 2026-08-17 under the §3 rule. Each finding's shipped fix was re-derived from source and, where a
guard existed, the guard was tested by planting the original defect. Verdicts:

### C1 · Executive Summary Roth headline — **fix confirmed**

`sum(roth_conv) * 0.22` is gone. `sheets_summary_builder.py:118` calls
`summary_figures.roth_strategy_benefit(c)`, which reads the Sheet 11 candidate contract and returns
the selected-versus-next-best deltas in both lifetime tax and after-tax terminal net worth — the
review's recommendation (a). It returns `None` below two candidates, so the "versus next best" row is
omitted rather than published against nothing. This is the shipped behavior, read at source.

### C2 · Hardcoded client-independent dollars — **fix confirmed at the reported location, residuals elsewhere**

The Executive Summary block now derives from `summary_figures.credit_shelter_trust_savings`, which
scales with the user-editable `il_exempt`, and **Sheet 14 reads the same helper**
(`sheets_strategy.py:1445`) — the shared-helper structure documentation asked for, so the flagship
page and the estate sheet cannot drift apart the way `glossary.py`'s docstring records happening
before. Both render the 8% as explicitly approximate.

Two notes rather than defects: (i) the shared 8% average rate coexists with `core.illinois_estate_tax()`,
which computes the real graduated tax — the two sheets now agree with each other but not with the
engine's own capability, which is an upgrade path, not a contradiction, since it is labeled
approximate; (ii) the same hardcoded-dollar pattern survives on the insurance/estate sheet, outside
the range C2 cited. Logged as **P9** — this is the part of C2 that a location-scoped fix would always
have missed, and the reason a finding's *class* is worth grepping for, not just its line numbers.

### C5 · Nominal headline figures + inconsistent Roth objective — **engine fix confirmed; guard was vacuous**

The objective half is fixed, and fixed carefully. `after_tax_terminal_nw_pv` (`planning_engines.py:1917`)
is a **separate** variable from the reported `after_tax_terminal_nw`, and every one of the four
`terminal_component` branches — default, `MINIMIZE_LIFETIME_TAX`, `MAXIMIZE_TERMINAL_NET_WORTH`,
`MAXIMIZE_PTI` — uses the PV, at the same discount as `lifetime_tax` and `estate_tax_penalty`. The
reported figure and `post_tax_inheritance` stay nominal. All four branches checked individually.

**The guard, however, could not fail.** `test_terminal_component_is_discounted_below_nominal_after_tax_nw`
computed the present value itself and asserted `expected_pv < after_tax_terminal_nw`. For any positive
discount over any horizon longer than zero years that is arithmetically necessary. The test never read
`terminal_wealth_score`, `score`, or any other objective output.

Demonstrated rather than argued: reverting line 1917 to `after_tax_terminal_nw_pv = after_tax_terminal_nw`
restores C5's defect in full, and **both tests in the file stayed green**. Rewritten to assert that
`terminal_wealth_score` equals the PV under a pinned `MAXIMIZE_PTI` mode (known weight 1.0), and to
reject the nominal figure explicitly. Against the planted defect it now fails at
**6,185,244 vs 2,948,770** — the objective had been weighting plan-end wealth at 2.1× its present
value while the tax it costs was discounted, which is the exact bias C5 described.

`test_post_tax_inheritance_stays_nominal_not_discounted` was checked and left alone: it restates the
definition at `:2117`, but it would genuinely fail if PTI were discounted, so it is a real pin.

### What this says about the Q1 disposition

Q1 chose a standing rule over re-auditing C1/C2/C5 individually, on the reasoning that the rule
generalizes. The rule is right, but it is forward-looking — it governs verification written *after*
2026-08-17, and C5's guard was written before. Two of the three findings needed no action; the third
was carrying a guard with **the same defect as instance 3** ("a guard that cannot fail") in the
mechanism protecting it. So the audit was worth its M. The generalizable lesson is narrower than
"re-audit everything": **a guard written for a finding about unverified claims deserves the planted-defect
test before the finding is closed**, because that is exactly the context in which a green check is
least informative.
