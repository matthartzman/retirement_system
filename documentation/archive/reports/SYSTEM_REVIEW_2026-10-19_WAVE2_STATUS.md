# System Review 2026-10-19 — Wave 2 Status

Companion to `SYSTEM_REVIEW_2026-10-19.md` section 9 (Wave 2). Updated 2026-10-20 after Wave 1 (WI-010 to WI-016) merged to `main` (#233). Planner decisions are the owner's sign-offs given in session on 2026-10-20.

| Item | Status | Where |
|---|---|---|
| WI-017 | Done | PR #235 (`claude/wave2-docs`) |
| WI-018 to WI-021 | Done | PR #234 (`claude/wave2-ui`). Open call: the build overlay offers Hide, not a real server-side cancel |
| WI-022 | Done (measure only) | engine PR; impact table `SYSTEM_REVIEW_2026-10-19_WI022_IMPACT.md` |
| WI-023 | Done, re-pinned | engine PR (FIN-003) |
| WI-024 phase 1 (IRMAA) | Done, baselines re-recorded | engine PR |
| WI-024 phase 2 (NIIT, ACA, Social Security) | Done, re-pinned | engine PR |
| WI-025 | Done, no pin moved | engine PR |
| WI-023b (Roth LTCG cap basis) | Done, baselines re-recorded | engine PR |
| WI-026 | Done, merged | #232 |

## Engine chain (branch `claude/wave2-eng`)

Pins after WI-024 phase 2 (frozen sample plan): terminal NW 5,381,597.38; lifetime tax 1,237,081.61; Roth conversions 125,000. Each step was measured and signed off before its re-pin; per-step figures are in the impact document, sections 7 and 8.

WI-023b (planner decision): the Roth LTCG cap is measured from AGI less the standard deduction. Pins unchanged; baselines re-recorded. New `sample_frozen` baseline figures in the `golden_compare` pipeline: terminal NW 5,553,535.58; lifetime tax 1,102,384.42; Roth conversions 742,151.76 (+143,428.81, mostly 2027 to 2029). Monte Carlo within-tier-policy success -5.7 points, funded-as-asked +0.9; one IRMAA tier change (2045). Details: impact document, sections 9 and 9.1.

Decisions recorded: align the LTCG band tops to the verified 2026 dataset (98,900 / 613,700); change all FIN-003 call sites in one patch; stack qualified dividends and gains by the filing status in force for each year (this fixed a 2056 survivor-year error); measure NIIT, ACA and Social Security taxation as separate steps; re-pin in sequence; the closed-form conventions in the WI-022 fixtures are confirmed.

Notices retired per their triggers: N1 (WI-024 both phases), N2 (WI-023), N4 (WI-025). N3, N5, N6 and N7 stay. The `sample_frozen` phase baseline was re-recorded for structure only after merging main and retiring these notices; no figure moved.

## Open items

- The `[demo]` phase baseline cannot be checked or re-recorded where `input/demo` is absent. It needs recording on a machine that has it.
- CPA review of the phase 2 sample outputs is recommended, not blocking. Attorney review is not involved in this chain.
- Frozen-plan sensitivity: ACA and Social Security taxation steps have no effect on the frozen plan (no bridge years; taxable share already at 85%). They are covered by end-to-end tests on constructed households.
- Environmental test failures in the cloud sandbox (missing gitignored `input/`, Node packages, parallel-run flakes in tax-loss harvesting and state residency that pass alone) are unchanged from clean base.
