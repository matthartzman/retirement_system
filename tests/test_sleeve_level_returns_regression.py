"""Wave 3.5 (system review 2026-08-04, finding C3 /
engine-single-return-all-accounts, re-assessed effort L -> M in §2.5):
_account_return() has always read c['account_returns'], but nothing
populated it, so every account grew at one identical rate regardless of what
it actually held. This derives a per-account rate from each account's actual
holdings (client_holdings.csv -> security_master.csv asset class ->
capital_market_assumptions.csv expected return), anchored so the
dollar-weighted portfolio average still equals the user's configured
portfolio_nominal_return -- only the RELATIVE tilt between accounts is new.

Scope note: this covers the deterministic projection path only. The Monte
Carlo path's return_by_year override takes precedence over account_returns
in _account_return() (by design, for MC's own per-year draw), so MC-level
sleeve differentiation is a separate, larger follow-up (reshaping the
existing multivariate asset-class draw's weight vector into a weight
matrix) not included in this pass.
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

from conftest import TEST_INPUT_DIR


def sample_config():
    data = load_csv(TEST_INPUT_DIR / "client_data.csv")
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = ensure_engine_config(parse_client(data, ""), source="test")
    return c


def test_account_returns_populated_for_the_frozen_household():
    c = sample_config()
    account_returns = c.get("account_returns") or {}
    assert account_returns, "account_returns should be populated from actual holdings"


def test_account_returns_differ_between_accounts():
    # The whole point of the fix: not every account gets the identical rate.
    c = sample_config()
    rates = set(round(v, 6) for v in (c.get("account_returns") or {}).values())
    assert len(rates) > 1, "every account still grows at one identical rate"


def test_account_returns_average_back_to_the_configured_portfolio_return():
    # Anchoring principle: the dollar-weighted average across accounts must
    # reproduce the user's own configured c['ret'], not a disconnected
    # CMA-derived number -- only the relative spread between accounts is new.
    c = sample_config()
    account_returns = c.get("account_returns") or {}
    positions = c.get("positions") or {}
    total_val = 0.0
    weighted = 0.0
    for acct, rate in account_returns.items():
        val = float(c.get("balances", {}).get(acct, 0.0) or 0.0)
        if val <= 0:
            continue
        total_val += val
        weighted += val * rate
    assert total_val > 0
    blended = weighted / total_val
    assert abs(blended - c["ret"]) < 0.01


def test_account_return_falls_back_to_default_when_unpopulated():
    from src.planning_engines import _account_return
    c = {"account_returns": {}}
    assert _account_return(c, "Some_Account", 0.06) == 0.06


def test_mc_year_override_still_takes_precedence_over_account_returns():
    # Deliberate: MC's per-year draw must not be silently shadowed by the
    # new per-account rates -- see the scope note above.
    from src.planning_engines import _account_return
    c = {"account_returns": {"Acct": 0.03}, "return_by_year": {2030: 0.11}}
    assert _account_return(c, "Acct", 0.06, year=2030) == 0.11
