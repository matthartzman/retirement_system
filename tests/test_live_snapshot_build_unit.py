"""Live Snapshot build(): inputs + quotes + baseline -> the /api/live-snapshot body. No network."""
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
    assert rates == {"pre_tax_rate": 0.3, "ltcg_rate": 0.2, "annuity_basis": {}, "non_liquid_tax": {}}
    assert ls.tax_rates(tmp_path / "none", plan_ltcg="") == {"pre_tax_rate": 0.25, "ltcg_rate": 0.15,
                                                             "annuity_basis": {}, "non_liquid_tax": {}}


def test_tax_settings_carry_annuity_basis_and_overrides(tmp_path):
    (tmp_path / "live_snapshot_settings.json").write_text(json.dumps(
        {"annuity_basis": {"Annuity - Matt": "120,000"}, "non_liquid_tax": {"Pension - Pat": "none", "Bad": "maybe"}}))
    rates = ls.tax_rates(tmp_path)
    assert rates["annuity_basis"] == {"Annuity - Matt": 120000.0}
    assert rates["non_liquid_tax"] == {"Pension - Pat": "none"}
