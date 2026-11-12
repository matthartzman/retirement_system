# Monte Carlo parity measurement (WI-009)

Paired-path gap, vectorized replay headline minus exact scalar, in percentage
points. Harness: `_paired_success` in
`tests/test_scalar_vectorized_paired_path_agreement_regression.py` (same paths
fed to both engines). Run 2026-10-19 on the frozen sample plan, n=200 paths,
30-year horizon, survivor economics on, wellness shocks off.

| Roth policy | seed 11 | seed 5 | seed 3 | max abs gap | path agreement |
|---|---|---|---|---|---|
| none | +0.5 | +2.5 | -1.5 | 2.5 | 95.5-97.5% |
| fill_to_bracket | 0.0 | 0.0 | -3.0 | 3.0 | 97.0-100% |
| optimize_terminal_tax (shipped default) | +0.5 | +2.5 | -1.5 | 2.5 | 95.5-97.5% |

Limits, stated plainly:

- One household shape, three seeds, n=200 (standard error about 3pp per run).
  This is a spot measurement, not the n>=1000, 4+ shape study in WI-036.
- `none` and `optimize_terminal_tax` gave identical numbers on this fixture, so
  the optimizer probably selects no conversions here; the default regime is
  not exercised on a plan where it converts. Treat as weak evidence.
- The tier-shadow secondary figure (`success_rate_within_tier_policy`) was NOT
  measured. It is removed from the KPI tile and kept only as a diagnostic.

Consequence: the KPI shows "+/-5pp" only for the three policies above; any other
policy (fill_to_irmaa, fixed_dollar, ...) is labelled "directional". The table
lives in `MC_PARITY_DEMONSTRATED_POLICIES` (src/planning_engines.py) and
`MC_TOLERANCE_DEMONSTRATED_POLICIES` (frontend/js/dashboard_decomp_home_panels.js).
Set `mc_scalar_spotcheck_n` > 0 to have `monte_carlo` report a small-N scalar
gap in the `scalar_spotcheck` diagnostic field.
