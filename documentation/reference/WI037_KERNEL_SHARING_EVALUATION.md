# WI-037: sharing engine kernels with the vectorized Monte Carlo engine

Status: evaluation recorded 2026-10-21. Answers the last clause of WI-037 ("evaluate sharing kernels with the vectorized engine"). The cycle removal itself shipped in #253 (`src/engine_kernels.py`).

## What is already shared

The vectorized engine (`_mc_vectorized_projection` and `_mc_vectorized_sample_death_ages` in `src/planning_engines.py`) already calls these `engine_kernels` functions, so the deterministic and vectorized paths cannot drift on them:

| Kernel | Used by the vectorized engine for |
|---|---|
| `_mc_bucket_return_tilts`, `_mc_apply_bucket_growth` | Per-bucket growth tilt (asset location) |
| `_mortality_qx`, `_age_shift_for_member` | Death-year sampling |
| `hsa_unscheduled_draw_allowed` | HSA draw gating |
| `_apply_account_return_adjustments`, `sample_household_death_years` | The scalar path (`_run_one_mc_path`, `mc_scalar_spotcheck`) |

## What is not shared, and why

`apply_death_transition`, `compute_rmds`/`apply_rmds`, `withdraw_*`, `plan_roth_conversion`/`apply_roth_conversion` and `spending_guardrail_year` are written for one household and one path: they take a config mapping and a dict of account balances and branch per account. The vectorized engine instead evolves four tax buckets as arrays across paths and takes its year-by-year decisions from the deterministic engine's rows (the "replay" design).

Sharing them means rewriting each as an array-valued kernel over buckets, with a scalar wrapper that must reproduce today's output to the cent. That is the "per-path engine" question (FIN-002 / ARC-002, options 2 and 3) that WI-036 left as an owner decision. Doing it piecemeal would add a second implementation of each kernel without removing the first.

## Conclusion

- The kernel split removes the import cycle that blocked sharing; nothing in `engine_kernels` now prevents it.
- The growth, mortality and HSA-gate kernels are already shared.
- Sharing the withdrawal, RMD, death-transition and Roth kernels is not worth doing on its own. It should be scoped with the WI-036 headline repair decision (funded-as-asked replay versus the scalar engine as engine of record), because that decision changes which kernels the vectorized path needs at all.
- Recommended next step: put the WI-036 repair decision to the owner; open a new WI for array-valued kernels only if the answer is a per-path vectorized engine.
