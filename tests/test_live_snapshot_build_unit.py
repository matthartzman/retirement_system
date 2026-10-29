"""Current Snapshot build(): inputs + quotes + baseline -> the /api/live-snapshot body. No network."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from financial_trends_reporter import live_snapshot as ls
from tests.test_live_snapshot_compute_unit import ACCOUNTS, BASELINE, FLOWS, LOTS, MONARCH, QUOTES, SECURITY_MASTER, TAX

NOW = datetime(2026, 10, 27, 15, 18, 4, tzinfo=timezone.utc)   # 11:18 ET, market open


class FakeQuotes:
    def __init__(self, quotes):
        self.quotes, self.calls = quotes, []

    def get(self, symbols, *, force=False):
        self.calls.append((sorted(symbols), force))
        return {s: self.quotes[s] for s in symbols if s in self.quotes}

    def age_seconds(self, symbols):
        return 12.0


INPUTS = {"lots": LOTS, "security_master": SECURITY_MASTER, "accounts": ACCOUNTS, "flows_daily": FLOWS,
          "monarch": MONARCH, "tax_rates": TAX, "log_as_of": "2026-10-26"}
INDEX_QUOTES = {"^GSPC": {"price": 6800.0, "previous_close": 6751.4, "stale": False},
                "^DJI": {"price": 47000.0, "previous_close": 46948.0, "stale": False}}


@pytest.fixture
def data_dir(tmp_path):
    (tmp_path / "baseline_prices_2026.json").write_text(json.dumps({"baseline_date": "2025-12-31", "prices": BASELINE["prices"]}))
    return tmp_path


def _build(data_dir, quotes=None, **kw):
    fake = FakeQuotes({**QUOTES, **INDEX_QUOTES} if quotes is None else quotes)
    out = ls.build(inputs=INPUTS, quote_cache=fake, data_dir=data_dir, now=NOW,
                   previous_close_lookup=kw.pop("previous_close_lookup", lambda symbols, today: {}), **kw)
    return out, fake


def test_build_header_fields(data_dir):
    out, fake = _build(data_dir)
    assert out["as_of"] == "2026-10-27T15:18:04Z"
    assert out["market"]["state"] == "open"
    assert out["delayed_minutes"] == 15
    assert out["quotes_age_seconds"] == 12.0
    assert out["baseline_date"] == "2025-12-31"
    assert out["liquid"]["current"] == pytest.approx(32200)   # same inputs as the compute fixture
    assert fake.calls == [(["AVUV", "ITOT", "IXUS", "^DJI", "^GSPC", "^IXIC"], False)]


def test_indices(data_dir):
    out, _ = _build(data_dir)
    gspc = next(i for i in out["indices"] if i["symbol"] == "^GSPC")
    assert gspc["label"] == "S&P 500"
    assert gspc["day_pct"] == pytest.approx(6800 / 6751.4 - 1)
    nasdaq = next(i for i in out["indices"] if i["symbol"] == "^IXIC")
    assert nasdaq["price"] is None and nasdaq["day_pct"] is None


def test_force_passes_through(data_dir):
    _, fake = _build(data_dir, force=True)
    assert fake.calls[0][1] is True


def test_previous_close_filled_from_snapshots_when_quote_lacks_it(data_dir):
    quotes = {**QUOTES, "ITOT": {**QUOTES["ITOT"], "previous_close": None}}
    out, _ = _build(data_dir, quotes=quotes, previous_close_lookup=lambda symbols, today: {"ITOT": 129.0} if "ITOT" in symbols else {})
    assert out["liquid"]["day"] == pytest.approx(100)


def test_inputs_error_is_reported_not_raised(data_dir):
    out = ls.build(inputs={"error": "plan store locked"}, quote_cache=FakeQuotes({}), data_dir=data_dir, now=NOW)
    assert out["error"] == "plan store locked"
    assert out["market"]["state"] == "open"


def test_tax_rates_settings_file_overrides(tmp_path):
    (tmp_path / "live_snapshot_settings.json").write_text(json.dumps({"pre_tax_rate": 0.3}))
    rates = ls.tax_rates(tmp_path, plan_ltcg="20.00%")
    assert rates == {"pre_tax_rate": 0.3, "ltcg_rate": 0.2, "annuity_basis": {}, "non_liquid_tax": {}, "explicit": ["pre_tax_rate"]}
    assert ls.tax_rates(tmp_path / "none", plan_ltcg="") == {"pre_tax_rate": 0.25, "ltcg_rate": 0.15,
                                                             "annuity_basis": {}, "non_liquid_tax": {}, "explicit": []}


def test_tax_settings_carry_annuity_basis_and_overrides(tmp_path):
    (tmp_path / "live_snapshot_settings.json").write_text(json.dumps(
        {"annuity_basis": {"Annuity - Matt": "120,000"}, "non_liquid_tax": {"Pension - Pat": "none", "Bad": "maybe"}}))
    rates = ls.tax_rates(tmp_path)
    assert rates["annuity_basis"] == {"Annuity - Matt": 120000.0}
    assert rates["non_liquid_tax"] == {"Pension - Pat": "none"}


# ---- friendly account labels ----

def test_household_nicknames_fall_back_to_first_name():
    plan = {("Household", "", "member_1_nickname"): "Matt", ("Household", "", "member_1_name"): "Matthew Hartzman",
            ("Household", "", "member_2_name"): "Patricia Hartzman"}
    assert ls.household_nicknames(plan) == {"h_nick": "Matt", "w_nick": "Patricia"}


def test_account_labels_use_the_planner_display_rule():
    people = {"h_nick": "Matt", "w_nick": "Pat"}
    labels = ls.account_labels(["Member_1_401k", " Member_2_Roth ", "Family_Checking", "", None], people)
    assert labels == {"Family_Checking": "Family Checking", "Member_1_401k": "Matt 401k", "Member_2_Roth": "Pat Roth"}


def test_build_ships_a_label_for_every_holdings_account(data_dir):
    fake = FakeQuotes({**QUOTES, **INDEX_QUOTES})
    out = ls.build(inputs={**INPUTS, "people": {"h_nick": "Matt", "w_nick": "Pat"}}, quote_cache=fake, data_dir=data_dir,
                   now=NOW, previous_close_lookup=lambda symbols, today: {})
    accounts = {str(l["account"]).strip() for l in LOTS}
    assert set(out["account_labels"]) == accounts
    assert out["account_labels"]["Member_1_IRA"] == "Matt IRA"


def test_build_fetches_closes_only_for_balances_older_than_the_previous_session(data_dir):
    asked = []
    monarch = {**MONARCH, "by_account": [{**r, "as_of": "2026-10-22"} if r["account"] == "IRA - Matt" else r
                                         for r in MONARCH["by_account"]]}

    def close_lookup(symbols, day):
        asked.append(day.isoformat())
        return {"ITOT": 125.0, "IXUS": 65.0}

    out = ls.build(inputs={**INPUTS, "monarch": monarch}, quote_cache=FakeQuotes({**QUOTES, **INDEX_QUOTES}),
                   data_dir=data_dir, now=NOW, previous_close_lookup=lambda symbols, today: {}, close_lookup=close_lookup)
    assert asked == ["2026-10-22"]
    ira = next(a for a in out["reconciliation"]["accounts"] if a["holdings_account"] == "Member_1_IRA")
    assert ira["holdings_value"] == pytest.approx(25500.0)
    _build(data_dir, close_lookup=close_lookup)   # every balance fresh: nothing fetched
    assert asked == ["2026-10-22"]


# ---- Time scope: the page's scope start date sets the Start values ----

def test_start_day_for_scope():
    from datetime import date
    today = date(2026, 10, 27)
    assert ls.start_day_for("2026-09-27", today) == date(2026, 9, 25)   # close before the 1st day: Sat 9/26 -> Fri
    assert ls.start_day_for("2026-01-01", today) == date(2025, 12, 31)  # YTD is the 12/31 close
    for bad in (None, "", "nonsense", "2026-10-27", "2026-11-01"):
        assert ls.start_day_for(bad, today) == date(2025, 12, 31)       # no usable start: year to date


def test_build_with_scope_start_prices_lots_at_that_close(data_dir):
    asked = []

    def closes(symbols, day):
        asked.append(day.isoformat())
        return {"ITOT": 125.0, "IXUS": 62.0} if day.isoformat() == "2026-09-25" else {}

    out, _ = _build(data_dir, start_from="2026-09-27", close_lookup=closes)
    assert out["baseline_date"] == "2026-09-25"
    assert "2026-09-25" in asked
    assert out["baseline_missing"] == ["AVUV"]          # bought 3/1, held at 9/25, no close found: listed
    # ITOT and IXUS at the 9/25 close; AVUV (no close) at cost; CASH at 1.
    assert out["liquid"]["start"] == pytest.approx(100 * 125.0 + 200 * 62.0 + 50 * 80 + 1000)
    assert out["liquid"]["new_money"] == 0               # every lot was bought before 9/25


def test_build_without_scope_is_year_to_date(data_dir):
    out, _ = _build(data_dir, start_from="")
    assert out["baseline_date"] == "2025-12-31"
