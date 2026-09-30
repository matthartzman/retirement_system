# Backlog of deferred work

Deferred items that are not in flight. The repository has no GitHub issue
tracker, so this file is the tracker: when an item is picked up, move it to a
spec or plan and delete the line here. Source for the first entries is
`docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
section 9.

| Item | Origin | Note |
|---|---|---|
| Automatic Move-2 strategy selection (try `cross_product`, fall back to `anchored` above `MOVE2_CROSS_PRODUCT_CAP`, report which ran) | #331 | Excluded from H2/A3 as scope expansion. |
| Chain the two housing engines (location search feeding the schedule search) | #329 | Not planned. |
| YTD writeback driven by confirmed broker fills | #329 | Not planned. |
| General stress-remediation optimizer | #329 | Not planned. |
| Server-side Planning Cases | #329 | Not planned. |
| Mark Build History snapshots unreproducible when their module set no longer matches | #330 | Not planned. |
| Data-conditional auto-off of modules | #330 | Not planned. |
| Confirm the disposition of #333 | taxonomy-and-spending-restructure spec | No spec, commit or PR references it. |
| Close the vectorized-vs-scalar Monte Carlo success-rate level bias (~14-18 pp optimistic on the frozen fixture; same issue as the widened drift gate in `test_monte_carlo_default_engine_mode.py`) | system review 2026-09-25-2 QA-006 | Investigation in a separate session; see `N1_MC_PARITY_DIAGNOSTIC_2026-09-07.md`. |
