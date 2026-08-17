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
- Asset **allocation de-risking within the MC** is still invisible. A cash reserve, a bond tent, or
  any bucket strategy produces **no sequence-of-returns protection** in the success rate, because the
  reserve crashes in lockstep with equities, merely offset.
- Therefore: **do not ship any recommendation whose justification is that a cash reserve or glidepath
  reduces failure risk, and cite the MC success rate as evidence.** The engine cannot see that effect.
  Recommendations resting on asset *location* are supported.

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
| P3 | **Rename `test_..._and_market_neutral`** (S3). Neutrality is now genuinely covered by P2's file, so all that remains is dropping the false half of the name — it tests dollar weighting, and should say so. | XS | sonnet · low |
| P4 | **Record the S1 substitution** in the plan, `GOLDEN_MASTER_CHANGELOG.md` and project memory: MC models asset *location* via mean shift, not sleeve variance. Add the "no cash-reserve/glidepath claims from the success rate" constraint to the MC methodology note in the client deliverable. | S | sonnet · medium |
| P5 | Reconcile the cash-account tilt divergence between the scalar and vectorized MC paths (S5). | XS | sonnet · low |
| P6 | Optional: source-level second look at C1, C2, C5 under the §3 rule. Deferred by the Q1 disposition. | M | opus · high |

**P4 is the one with a client-facing deadline** — it is a disclosure, and the next build ships without
it otherwise.
