# Genuinely Redirecting Withdrawal Requests by Tier Priority — Spec

Next increment named in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s
"Not done" list: *"Genuinely redirecting withdrawal requests (not just
reporting attribution) by tier priority inside the MC engines — which
bucket (taxable/pretax/roth/cash/HSA) gets drawn down to fund which tier...
Still a much larger, riskier rewrite than the reporting-only additions
above — treat as its own project, not a quick follow-on."*

**Spec/research only — no code in this document.** Research delegated to
an Explore subagent for the mechanical grounding; the design analysis below
is original.

## What exists today (verified against the code)

### Deterministic engine: no cut mechanism at all

`total_spend_need` (`deterministic_engine.py:1527-1531`, recomputed
identically at 1727-1731) is one blended scalar — `spend_base` + recurring
extras + lump + housing + `ltc_prem_yr` + wellness + HELOC + business
expenses. The withdrawal cascade (Priority 1 RMD → 1b contingent-liability
HSA → 2 scheduled HSA → 3 pretax elective → 4 taxable/trust → 4b final
pretax → 4c final HSA → 5 Roth) drains a single `gap` scalar
(`row['total_cash_need'] - income_from_streams`) through each step in turn.
**There is no partial-funding path.** Whatever `gap` survives Priority 5
becomes `row['unfunded_gap'] = max(0.0, gap)` — one residual number, never
tier-tagged, never fed back to reduce spending. `row['spend_by_tier']` is
explicitly "purely additive reporting: it never feeds back into
total_spend_need, withdrawals, or taxes" (`deterministic_engine.py:1742-
1743`). This item's own "Not done" wording scopes it to "inside the MC
engines," so the deterministic engine's all-or-`unfunded_gap` behavior is
out of scope here — treated as a separate, unrelated design question.

### MC engines: a uniform scalar, not a tier-aware reconstruction

Only `_mc_vectorized_projection` has a cut mechanism (`spend_cut_frac`,
`planning_engines.py:4090` on); `monte_carlo_exact_scalar` has none — a
pre-existing parity gap worth noting but not this spec's problem to solve.

The critical mechanic, `planning_engines.py:4159-4165`:

```python
planned = {
    'taxable': eff['withdrawals']['taxable'][:, j] * spending_scale[:, j] * cut_mult,
    'pretax':  eff['withdrawals']['pretax'][:, j]  * spending_scale[:, j] * cut_mult,
    'roth':    eff['withdrawals']['roth'][:, j]    * spending_scale[:, j] * cut_mult,
    'hsa':     eff['withdrawals']['hsa'][:, j] * med_idx[:, j] / det_idx[:, j],
    'cash':    eff['withdrawals']['cash'][:, j] * spending_scale[:, j] * cut_mult,
}
```

`eff['withdrawals'][bucket]` is the **deterministic engine's own,
already-decided per-bucket split** for that row — the real HSA→pretax→
taxable→Roth-last cascade's output, replayed forward (the same "replay the
real plan" pattern `withdrawal_strategy_comparison.py`'s `current_plan`
strategy uses). `cut_mult = 1 - spend_cut_frac` is then applied as **the
same scalar multiplier to every non-HSA bucket, uniformly**.

Then, entirely after the bucket-draw recursion for the year has already
run and `balances`/`out['unfunded']` are finalized, `_mc_tier_priority_
retained` (`planning_engines.py:3997-4054`, called at `4235`) computes what
each tier's spending *would* be if the same total dollar cut were applied
by priority (discretionary first, essential protected last) instead of
uniformly — but only to populate `spend_{tier}_real` and the essential-
shortfall reporting fields. Its own docstring is explicit: *"The combined
total across ALL tiers is unchanged either way... this only changes how
the same dollar cut is attributed across tiers, never the total. It
therefore never affects out['taxable']/'pretax'/'roth'/'cash']/'liquid'/
'total'/'unfunded'/'path_success'/'success_rate'."*

**The inconsistency this spec addresses**: the reported story ("this year,
the cut fell on discretionary spending, essential was protected") and the
simulated reality (every bucket, Roth included, was scaled down by the
identical percentage regardless of tier) are two different computations
that happen to share a total. Nothing the household's balances/success
rate/terminal wealth reflects actually incorporates tier priority — only
the labels painted on top of an unrelated uniform-scaling result do.

### The existing precedent: `fund_contingent_liability_from_hsa`

Priority 1b in the deterministic engine (`planning_engines.py:1129`,
called at `deterministic_engine.py:2122`) is genuine redirection for one
tier: it identifies `contingent_liability`'s dollar need
(`ltc_prem_yr + wellness_shock_yr`) and funds it from a *specific* bucket
(HSA, bank/floor-capped) *ahead of* the general cascade, reducing `gap`
directly. The MC engine's analogue (`_mc_vectorized_projection:4169-4185`)
draws sampled wellness shocks from HSA first, gated the same way. This is
the shape "genuine redirection" already takes for one tier — and per
`OPTIMIZATION_REFACTOR_STATUS.md:311-316`, even this one case has an
acknowledged parity gap (the MC engines reimplement it inline rather than
calling the shared function).

## The real design question: what should change?

`_mc_tier_priority_retained`'s own proof — *the total dollar cut is
identical whether uniform or tier-prioritized* — means the fix is not
"request less money overall." It is about **which bucket absorbs the
reduction**, and there are two genuinely different readings of that,
which the "Not done" item's own wording ("which bucket... gets drawn down
to fund which tier") does not disambiguate:

**Reading A — protect the *cascade's own priority*, not a new tier→bucket
map.** The deterministic engine's HSA→pretax→taxable→Roth-last order
already encodes a philosophy: Roth is the account you draw last, because
its tax-free growth is worth preserving longest. `eff['withdrawals']
['roth']` for a given row is only nonzero once HSA/pretax/taxable were
insufficient — i.e., it already represents the marginal, last-resort
draw. Uniformly scaling every bucket by the same `cut_mult` cuts Roth by
the same *percentage* as HSA, which is inconsistent with that philosophy:
if the household is spending less this year, the honest re-derivation is
closer to "HSA/pretax/taxable stay close to their original draws, and
Roth — the marginal bucket — absorbs most or all of the reduction,"
because that is what re-running the *same* cascade against a smaller
total would produce. This reading needs no tier taxonomy at all; it is a
correction to how a cut interacts with the *existing* account cascade.

**Reading B — a genuine tier→bucket policy, extending PR #66's pattern.**
Discretionary spending should perhaps never draw down Roth at all — if
there isn't enough taxable/pretax capacity left to fund a vacation, the
vacation should be the thing that doesn't happen, not "the household
draws some Roth for it because the blended cut left some Roth capacity."
This requires deciding, as a financial-planning policy, which bucket(s)
each tier is allowed to draw — essential potentially funds from anywhere
(including Roth, as a genuine last resort); discretionary funds only from
taxable/pretax and is capped, not backstopped by Roth, when those run
short.

These two readings produce different mechanisms and different numbers,
and neither is obviously "the" intended one from the existing docs. This
is the central open question this spec cannot resolve alone — see
"Open questions" below.

## Why this is genuinely a larger rewrite (concrete blast radius)

- **Vectorized re-derivation is nontrivial.** Reading A requires
  re-running an order-dependent cascade (not a linear scale) across
  `n_sims` paths simultaneously per year — today's `planned[bucket] =
  eff['withdrawals'][bucket] * cut_mult` is a single vectorized multiply;
  a cascade-aware version needs, per path, to know each bucket's
  *capacity* this year (its balance) and re-walk HSA→pretax→taxable→Roth
  against a smaller total, which is exactly the kind of per-path
  sequential logic vectorization exists to avoid. `monte_carlo_exact_
  scalar` (no `spend_cut_frac` today) would need the same logic built from
  scratch, in its per-path Python loop, to keep the two engines
  consistent — the same "engines cannot disagree about the same tier"
  principle PR #66 established for the HSA-first gate.
- **Reading B requires a real product decision** (does essential *ever*
  draw Roth? does important? what happens when a tier's allowed buckets
  are all exhausted — does it become a genuine shortfall, or fall through
  to the next tier's buckets?) that is a financial-planning judgment call,
  not an engineering one, and should not be guessed at by an
  implementation.
- **Existing tests encode the current (uniform) behavior as an
  invariant** and would need deliberate, understood changes, not just
  updated expected values:
  - `tests/test_mc_tier_priority_cut_regression.py` — its own docstring:
    *"deliberately still a reporting/attribution change, not a change to
    withdrawal totals: for a fixed spend_cut_frac, the aggregate dollars
    pulled from taxable/pretax/roth/cash and hence unfunded/liquid/total/
    success_rate are unaffected by which tier absorbs the cut."* This
    sentence becomes false under either reading — the file's central
    thesis inverts, not just its assertions.
  - `test_total_retained_matches_uniform_reduction`,
    `test_no_cut_is_bit_identical_to_pre_change_behavior`,
    `test_spend_total_real_unaffected_by_tier_priority_attribution` (same
    file) all assert the bit-identical/uniform-total invariant directly.
  - `tests/test_optimization_phase1_mc_spend_by_tier.py::
    test_spend_cut_frac_scales_real_spend_down`,
    `tests/test_mc_required_cut_distribution.py` (docstring: `spend_cut_frac`
    is "otherwise a[n] uniform reduction"), and
    `tests/test_sustainable_spending_solve_regression.py` all encode the
    uniform-cut assumption at the batch-search level that sizes
    `spend_cut_frac` in the first place — a Reading-A/B change could shift
    what dollar `cut_frac` is *needed* to hit a given success rate, since
    success/failure now depends on which buckets actually absorb it.
  - `tests/test_essential_discretionary_floor_regression.py` (docstring:
    *"A uniform spend_cut_frac (from sustainable_spending_solve / Sheet
    15 B3/B4)"*) is the dashboard-facing consumer of this exact
    assumption.
- **Success-rate movement is expected, not a bug to chase.** If Roth is
  protected more (Reading A) or discretionary genuinely stops drawing
  Roth (Reading B), `success_rate`/`unfunded` computations that depend on
  bucket balances surviving to later years will differ from today's
  uniform-scaling baseline — this is the point of the change, but means
  the golden-master/regression-suite blast radius is not confined to
  reporting fields the way every prior increment in this refactor has
  been (PR #64's own docstring proof that totals stay bit-identical does
  NOT extend to whichever design is chosen here).

## Options

**Option A — Cascade-consistent uniform cut (Reading A only).** Re-derive
`planned[bucket]` for a cut year by walking the same HSA→pretax→taxable→
Roth order against the reduced total (`total_scaled * cut_mult`, still a
single number — no tier taxonomy needed), instead of linearly scaling each
already-decided bucket amount. Smaller in scope than Option B: no new
policy surface, no tier→bucket mapping, just makes the *existing* cascade
philosophy (Roth-last) hold under a cut the way it already holds for the
full, uncut request. Vectorizing this is still real work (an order-
dependent walk per path per year, using that path's own current balances),
but it's a bounded, well-specified problem with an existing pattern to
follow (`_mc_apply_withdrawal_bucket`, already used for the cascade order
inside the per-year loop).

**Option B — Genuine tier→bucket policy (Reading B).** Assign each tier an
allowed funding order (e.g., essential: HSA→pretax→taxable→Roth as today;
important: HSA→pretax→taxable, Roth only as an explicit last resort;
discretionary: taxable/pretax only, never Roth, and simply doesn't happen
if those are exhausted). Strictly larger than Option A: needs the product/
financial-planning decision named above, a new per-tier policy
configuration surface (hardcoded four-tier default vs. a household-
configurable override — another open question), and re-derivation logic
that additionally branches on tier, not just re-running one cascade.
Subsumes Option A as a special case if every tier is given the same
allowed-bucket order.

**Option C — Do not build either yet; keep the current reporting-only
behavior and its known caveat.** The existing `_mc_tier_priority_
retained` framing is honestly documented as attribution-only, not
misrepresented as more than it is (its own docstring says so directly,
and the "Not done" list already flags the gap). Defer until a concrete
consumer of tier-accurate success rates (e.g., a planner-facing feature
that specifically claims "essential spending survives at X% confidence")
makes the inconsistency between reported and simulated behavior actually
matter to a user-facing number, rather than building it speculatively.

## Recommendation

**Scope down to Option A first, and treat Option B as a distinct,
later decision** requiring explicit product/financial-planning
sign-off before any code — for the same reason this refactor has
repeatedly separated "close a correctness gap" from "add a new policy
surface" (the double-dip fix vs. the deferred HSA-bank-accumulation
follow-on is the clearest precedent). Option A closes the specific
inconsistency this spec identifies (reported tier attribution vs.
simulated bucket behavior disagreeing) without inventing a new tier→
bucket policy that would itself need a design conversation. It is still
"a much larger, riskier rewrite than the reporting-only additions above,"
as the existing doc says — real vectorization work, not a quick
follow-on — but it has one clear, well-specified target instead of an
open product question.

## Open questions

1. **Does Option A alone satisfy the "Not done" item's intent**, or was
   "which bucket gets drawn down to fund which tier" always pointing at
   Option B specifically? The wording supports either reading; only the
   person who wrote that roadmap line (or a fresh product decision) can
   resolve it.
2. **`monte_carlo_exact_scalar` parity.** Should this land in the
   vectorized engine only (matching where `spend_cut_frac` exists today),
   with scalar-engine parity as an explicit, separately-scoped follow-up
   the way HSA-engine-parity was deferred in the expense-bank increment —
   or does inconsistency between the two engines' cut behavior recreate
   the same "engines disagree about the same tier" class of bug PR #66
   fixed for HSA?
3. **Interaction with `sustainable_spending_solve`'s binary search.** That
   search sizes `spend_cut_frac` to hit a target success rate under
   *today's* uniform-scaling behavior. If Option A changes how a given
   `cut_frac` translates into `unfunded`/`success_rate`, does the search
   still converge correctly, and do its own tests
   (`tests/test_sustainable_spending_solve_regression.py`) need new
   fixtures rather than just updated numbers?
4. **Is a "genuine shortfall" possible under Option A/B that wasn't
   before?** Today, a bucket running dry mid-cascade falls through to the
   next bucket in order; under a tier-restricted policy (Option B),
   deliberately NOT falling through (discretionary never touches Roth)
   could produce more `unfunded` years for the same `spend_cut_frac` than
   today — is that the correct, more-honest behavior, or does it need its
   own floor/guard the way `liquidity_reserve_floor` protects other
   buckets?
