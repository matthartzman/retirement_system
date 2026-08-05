"""Wave 5.2 (system review 2026-08-04, planner finding
withdrawal-sequencing-not-comparable): "Named strategies, not free
reordering." The real engine's withdrawal cascade (HSA -> pretax elective
-> taxable trust -> Roth-last) has multi-round tax true-up math (ordinary
income, then LTCG/NIIT) written assuming that exact order -- genuinely
offering named strategies THE ENGINE executes would mean re-deriving that
math per order, real engine-rewrite risk for a comparison feature.

src/withdrawal_strategy_comparison.py answers the planner's actual
question -- how would spending from these accounts in a different order
compare? -- as a deliberately separate, lower-fidelity tool: it reuses the
real plan's own RMD and total-elective-withdrawal-need figures per year
(not re-derived), and only varies which accounts fund that already-known
need under each named strategy, with a simplified flat-rate tax model.

Two real bugs were found and fixed while building this against the frozen
fixture (not just unit-tested against synthetic numbers):
1. The "current_plan" strategy initially re-derived an allocation from the
   summed elective_need through this module's own strategy-order logic,
   rather than using the real plan's actual per-account withdrawal split
   (ira_wd/trust_wd/roth_wd) directly -- so even the "baseline" comparison
   point didn't match the real plan it was supposed to represent.
2. A flat single growth rate for all three account buckets understated
   growth enough (vs. Wave 3.5's per-account differentiated returns) that
   the simulated household appeared to deplete near the end of the plan
   when the real engine shows it staying solvent; fixed by reusing
   c['account_returns'] for a balance-weighted per-bucket rate.
3. When the "current_plan" strategy's real per-account split couldn't be
   funded from a bucket that had simulator-drifted lower than the real
   engine's own trajectory, the shortfall was reported as unfunded instead
   of falling back to whichever bucket still had room -- fixed with a
   fallback cascade, matching how every other strategy already handles a
   depleted bucket.
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.withdrawal_strategy_comparison import (
    WITHDRAWAL_STRATEGIES,
    compare_withdrawal_strategies,
    simulate_withdrawal_strategy,
)
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

from conftest import TEST_INPUT_DIR


def sample_config_and_rows():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c = ensure_engine_config(c, source="test")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(c)
    return c, rows


def test_all_four_named_strategies_present():
    c, rows = sample_config_and_rows()
    results = compare_withdrawal_strategies(c, rows)
    assert {r["strategy_key"] for r in results} == set(WITHDRAWAL_STRATEGIES.keys())


def test_current_plan_baseline_has_no_shortfall_matching_the_real_solvent_plan():
    # Regression test for bug #1/#3 above: the frozen household's real plan
    # has zero failures (PINNED_FAILURES == [] in test_199), so the
    # "current_plan" approximation -- which is supposed to represent that
    # same real plan, not a counterfactual -- should not show a shortfall.
    c, rows = sample_config_and_rows()
    result = simulate_withdrawal_strategy(c, rows, "current_plan")
    assert result["years_with_shortfall"] == 0


def test_current_plan_terminal_portfolio_is_same_order_of_magnitude_as_real():
    # Not exact (deliberately lower-fidelity), but should be within a
    # reasonable band of the real engine's own portfolio-only terminal
    # value (pretax_nw + roth_nw + trust_nw, excluding annuities/home
    # equity/other non-portfolio wealth this module doesn't track).
    c, rows = sample_config_and_rows()
    real_portfolio_terminal = (
        float(rows[-1].get("pretax_nw", 0.0) or 0.0)
        + float(rows[-1].get("roth_nw", 0.0) or 0.0)
        + float(rows[-1].get("trust_nw", 0.0) or 0.0)
    )
    result = simulate_withdrawal_strategy(c, rows, "current_plan")
    approx_terminal = result["terminal_total_nw_approx"]
    assert real_portfolio_terminal > 0
    assert 0.1 * real_portfolio_terminal <= approx_terminal <= 2.0 * real_portfolio_terminal


def test_roth_first_never_beats_current_plan_on_lifetime_tax():
    # Directional sanity: spending Roth first (giving up its tax-free
    # compounding earliest) should never show LOWER approximate lifetime
    # tax than the plan's own Roth-last sequencing for this household.
    c, rows = sample_config_and_rows()
    current = simulate_withdrawal_strategy(c, rows, "current_plan")
    roth_first = simulate_withdrawal_strategy(c, rows, "roth_first")
    assert roth_first["lifetime_tax_approx"] >= current["lifetime_tax_approx"]


def test_compare_sorts_by_ascending_lifetime_tax():
    c, rows = sample_config_and_rows()
    results = compare_withdrawal_strategies(c, rows)
    taxes = [r["lifetime_tax_approx"] for r in results]
    assert taxes == sorted(taxes)


def test_no_bucket_left_with_room_while_reporting_a_shortfall():
    # Regression test for bug #3: a strategy must never report unfunded
    # need in a year while one of its own tracked buckets still has a
    # positive balance -- that would mean a fundable dollar was left on
    # the table instead of being drawn.
    c, rows = sample_config_and_rows()
    for key in WITHDRAWAL_STRATEGIES:
        result = simulate_withdrawal_strategy(c, rows, key)
        for y in result["yearly"]:
            if y["unfunded"] > 1.0:
                assert y["pretax"] < 1.0 and y["roth"] < 1.0 and y["taxable"] < 1.0, (
                    f"{key} year {y['year']}: reported unfunded={y['unfunded']:.0f} "
                    f"while a bucket still had room: {y}"
                )


def test_sheet9_renders_the_comparison_section():
    from openpyxl import Workbook
    from src.reporting.sheets_strategy import build_sheet9

    c, rows = sample_config_and_rows()
    wb = Workbook()
    ws = wb.active
    build_sheet9(ws, c, rows)
    text = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None]
    assert any("Withdrawal-Sequencing" in t for t in text)
    assert any("Current Plan" in t for t in text)
