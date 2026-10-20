# System Review 2026-10-19 — Wave 3 Status

Companion to `SYSTEM_REVIEW_2026-10-19.md` section 9 (Wave 3). Opened 2026-10-20 after Waves 0 to 2 merged (#238).

## Items

| Item | Status | Notes |
|---|---|---|
| WI-027 | Code done, awaiting planner sign-off on the impact table before any golden re-pin | Values below. FIN-009 credit-shelter arithmetic and the mortality table stay open. |
| WI-028, WI-029 | Not started | Serial after WI-027 (W3-A) |
| WI-031, WI-033 | Not started | Independent |
| WI-039 (new) | Not started | FIN-004: 10% additional tax on pre-59.5 distributions (WI-002(a) decided "in scope") |
| WI-040 (new) | Not started | FIN-007: Social Security earnings test (WI-002(b) decided "in scope") |
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
