# System Review 2026-10-19 — Wave 3 Status

Companion to `SYSTEM_REVIEW_2026-10-19.md` section 9 (Wave 3). Opened 2026-10-20 after Waves 0 to 2 merged (#238).

## Items

| Item | Status | Notes |
|---|---|---|
| WI-027 | Code done, awaiting planner sign-off on the impact table before any golden re-pin | Values below. FIN-009 credit-shelter arithmetic and the mortality table stay open. |
| WI-028, WI-029 | Not started | Serial after WI-027 (W3-A) |
| WI-031, WI-033 | Not started | Independent |
| WI-039 (new) | Code done; **demo golden baseline needs re-recording** | FIN-004: 10% additional tax on pre-59.5 distributions. Notice N3 retired. See the WI-039 section below. |
| WI-040 (new) | Done (no pin moved) | FIN-007: Social Security earnings test. Notice N5 retired. See the WI-040 section below. |
| WI-041 (new) | Done | UX-002 follow-up: real server-side build cancel (the Wave 2 overlay only hid the window) |

## New work items

WI-039 and WI-040 close a gap in the original plan: WI-002 put both in scope but only warning notices (N3, N5) shipped, and no later wave built them.

| ID | Change | Findings | Depends on | Priority | Effort | Validation | Model tier |
|---|---|---|---|---|---|---|---|
| WI-039 | Model the 10% additional tax on pre-59.5 pre-tax distributions and Roth-conversion distributions, with the IRC 72(t) exceptions the plan data can express (Rule of 55 separation, SEPP/72(t)(2)(A)(iv) as a user-entered schedule, disability). Retire notice N3 when shipped. | FIN-004 | WI-027 | P1 | L | Closed-form tests per exception; measure mode before any re-pin; CPA review of exceptions. | expert_reasoning |
| WI-040 | Model the Social Security earnings test (annual threshold and the year-of-FRA threshold, $1 withheld per $2 / $1 per $3, withheld benefits recomputed at FRA). Thresholds are dated rows. Retire notice N5 when shipped. | FIN-007 | WI-027 | P1 | M | Closed-form tests (below, in, and at-FRA year); measure mode; benefits counselor or CPA review. | expert_reasoning |
| WI-041 | Real build cancel: `POST /api/build/cancel/<job_id>` terminates the build process; the job ends as `cancelled`; the overlay offers Cancel build and Hide. | UX-002 | WI-019 | P2 | S | `tests/test_build_cancel_regression.py` | standard_reasoning |

Both engine items move goldens, so each needs a measured impact table and planner sign-off before its re-pin, as for WI-022 to WI-025. They need dated threshold values you verify: 2026 earnings-test limits (below FRA, year reaching FRA) and, for WI-039, confirmation of the exception list in scope.

## WI-027 values recorded (owner-supplied, reviewed 2026-10-20)

Sources are the public documents named in each dataset row. The per-row table the owner holds remains the audit copy.

| Family | Values |
|---|---|
| AMT 2026 (Rev. Proc. 2025-32 sec. 4.10) | Exemption 140,200 / 90,100 / 70,100 (MFJ / single / MFS); phase-out start 1,000,000 / 500,000 / 500,000 at 50%; rate break 244,500 (122,250 MFS). 2025 rate break corrected to 239,100 (232,600 was the 2024 value). |
| QLAC, QCD 2026 (Notice 2025-67) | QLAC 210,000 (unchanged); QCD 111,000 per individual |
| Student-loan interest 2026 (sec. 4.29) | Phase-out 175,000–205,000 MFJ; 85,000–100,000 other; maximum 2,500 (the thresholds are indexed; the old code did not index them) |
| NC, IN | 3.99% and 2.95% (state only) |
| California | FTB 2025 schedules carried forward as provisional; 1% Behavioral Health Services Tax over 1,000,000 added (verified for 2026) |
| New York | 2026 income-tax schedule (3.9 / 4.4 / 5.15 / 5.4 / 5.9% lower brackets); estate basic exclusion 7,350,000 (the 105% cliff boundary comes from a secondary source); no state portability. Section 601(d) benefit recapture and NYC/Yonkers taxes are not modeled. |
| Part D, wage base | Part D national base beneficiary premium 38.99 (2026); wage base 184,500 now marked verified |
| Federal estate | 15,000,000 per person; a blank exemption is now derived from the household (one person 15,000,000; couple 30,000,000). Explicit saved values are kept, and notice N6 now shows only for a one-person household with a larger explicit value. |

Open after WI-027:

- Mortality table: the embedded values are not reconciled to a source. Candidate replacement: the SSA period life table or the Trustees Report projected death probabilities (a modeling decision for the owner).
- Estate-attorney review of portability and credit-shelter arithmetic: not documented. The credit-shelter double count in FIN-009 is unchanged. Estate and legacy outputs that use a credit shelter trust are provisional and must not be represented as legally reviewed.
- California 2026 final schedule: replace the provisional 2025 carry-forward when the FTB publishes it.

## WI-040 — Social Security earnings test (FIN-007)

Owner decisions recorded 2026-10-20 ("accept all recommendations"; plan year 2025 will never be supported, so there are no 2025 rows):

| Decision | Implementation |
|---|---|
| Limits (2026) | 24,480 below full retirement age (FRA) all year; 65,160 in the FRA year. $1 withheld per $2 over (before the FRA year), $1 per $3 over (FRA year). Dated rows `ss_earnings_test_*` in `tax_law_v10.json`. **Status `assumption`**: the owner accepted the figures, but no retrieval date or verifier is recorded. Attach the SSA source and mark them verified when available. |
| Earnings counted | Wages, plus net self-employment earnings for a sole proprietor; S-corp salary only (distributions are not earnings). The plan holds one household earned-income stream that ends at member 1's last earned year, so the earnings belong to member 1. |
| FRA year | Earnings counted = full-year earnings × (months before the FRA month ÷ 12); benefits at risk are the same share of the year. |
| Withholding | A dollar reduction of the year's benefit, capped at the benefit payable. No whole-month rounding. |
| Credit at FRA | Months withheld (withheld dollars ÷ the month's benefit) shrink the early-claim reduction: from the year after the FRA year the benefit uses an effective claim age of the claim age plus months withheld ÷ 12, capped at FRA. |
| Years after 2026 | Limits compound by the plan's bracket inflation (the plan has no separate wage-growth assumption). |
| Scope | Member 1's own retirement benefit. **Not modeled:** spousal benefits payable on a working spouse's record (SSA also withholds those), disability benefits, and the FRA-year credit within the FRA year itself. |

Measured effect: the frozen sample plan and the demo plan show no engine-row change (neither claims early while earning), so no golden pin moves. The earnings-test projection tests are in `tests/test_wi040_ss_earnings_test_regression.py`. Notice N5 is retired; the spousal-record limitation has no notice yet, because notice wording is owner-approved text. Decide whether it needs one.

Planner sign-off on the design is still wanted, and a benefits counselor or CPA should review the rules.

## WI-039 — Additional 10% tax on early distributions (FIN-004)

Scope accepted by the owner 2026-10-20 (planner and CPA signed off on the design). Kernel: `src/early_distribution.py`.

| Exception | Modeled as |
|---|---|
| Age 59½ and later | No tax. In the year 59½ is reached, only the months before the birthday count (draws are assumed even through the year). |
| Rule of 55 | Per-member `separation_year`, valid when the member is 55 or older in that year; from then on the member's 401(k)/403(b) balances are exempt (IRAs are not). |
| Disability | Per-member `disability_start_year`; from then on all of the member's pre-tax draws are exempt. |
| SEPP | Per-member `sepp_start_year` and `sepp_annual_amount`; up to that amount of the member's pre-tax draws each year is exempt. The schedule is entered, never calculated; a modified schedule (recapture) is not modeled. |
| Death | A deceased owner has no draws. |
| Not modeled | Education, first home, birth/adoption, medical, QDRO, levy and the other 72(t) exceptions; the Roth-conversion five-year rule (Roth withdrawals are treated as exempt); state additional taxes; HSA non-medical withdrawals. |

Inputs are under Withdrawal Policy, subsections "Early Distributions Member 1" and "Early Distributions Member 2" (blank means no exception). The 10% is a dated, legislated row (`early_distribution_additional_tax_rate`).

How it enters the cascade: the tax is a separate term (never folded into federal tax). The IRA true-up loop prices it on the cumulative pre-tax draws by account, so the gap includes it and the next round of elective draws funds it, in both Priority 3 and Priority 4b. It joins `total_tax_pre_niit`, so every later stage sees it. Years with the tax carry `early_dist_tax` on the row and a named `early_distribution` line in the cash-flow tax breakdown. Plans with nobody under 59½ run through exactly the old code path.

Measured effect (same environment, before vs after): the frozen sample plan and all 10 synthetic golden scenarios do not move. The demo plan moves: additional tax 1,195.04 in 2026 and 17.55 in 2027; lifetime tax +1,305.13; terminal net worth −9,757.80 (16,786,034.80 → 16,776,277.00, local environment values).

**Golden baseline: not re-recorded.** `tests/fixtures/golden_phase_baseline/` for the demo plan must be re-recorded, and the local cloud environment cannot do that faithfully (it already differs from the committed baseline before this change). Run on a machine that matches CI: `python tools/golden_compare.py record --plan demo --reason "WI-039: 10% additional tax on early distributions (demo plan: 2026 1,195.04; 2027 17.55)"`, then commit the baseline. Planner sign-off on the impact table above is the remaining gate before that re-record.

Notice N3 is retired. A short replacement note for the exceptions not modeled needs owner-approved wording; none is added yet.
