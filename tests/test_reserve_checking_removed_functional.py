"""#339 spec §8 (2026-09-24 W-F Task F2): the Reserve Requirements "Checking
accounts" field (Other Assets,Cash,value) is not read by the engine --
c['cash_other'] comes from _Checking holdings accounts (src/data_io.py). This
removes the field from the demo plan, the UI and the schema, and adds an
import warning for a legacy plan that still carries a non-zero value with no
_Checking holdings account to receive it.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path

from src.data_io import parse_client, reserve_checking_import_warning

ROOT = Path(__file__).resolve().parents[1]

HEADER = "section,subsection,label,value,units,notes\nHousehold,,residence_state,Illinois,text,\n"


def _parse(csv_text: str):
    rows = list(csv.reader(io.StringIO(csv_text)))
    header = rows[0]
    data: dict = {}
    for row in rows[1:]:
        padded = row + [""] * max(0, len(header) - len(row))
        sec, sub, lbl, val = padded[0], padded[1], padded[2], padded[3]
        if not sec or sec.startswith("#") or not lbl:
            continue
        data.setdefault(sec, {}).setdefault(sub, {})[lbl] = val
    return parse_client(data, "", skip_live_pricing=True)


def test_demo_csv_has_no_checking_field():
    text = (ROOT / "input/demo/client_assets.csv").read_text(encoding="utf-8")
    assert "Other Assets,Cash,value" not in text


def test_schema_has_no_checking_field():
    text = (ROOT / "reference_data/schema.csv").read_text(encoding="utf-8")
    assert "Other Assets,Cash,value" not in text


def test_reserve_requirements_copy_does_not_mention_checking():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    start = js.index('id: "assets_home_cash"')
    end = js.index("\n  },", start)
    assert "checking" not in js[start:end].lower()


# ── reserve_checking_import_warning: the pure decision function ──────────

def test_no_warning_when_legacy_value_is_zero():
    assert reserve_checking_import_warning(0, {}) is None


def test_no_warning_when_a_checking_holdings_account_exists():
    assert reserve_checking_import_warning(25000, {"Family_Checking": 25000.0}) is None


def test_warns_naming_the_amount_and_investment_holdings():
    warning = reserve_checking_import_warning(25000, {"Joint_Trust": 500000.0})
    assert warning is not None
    assert "25,000" in warning
    assert "Investment Holdings" in warning


# ── end-to-end: parse_client wires the raw legacy field into the warning ──

def test_parse_client_warns_for_a_legacy_plan_with_no_checking_account(tmp_path, monkeypatch):
    # Isolate from the seeded test workspace (tests/conftest.py points
    # RETIREMENT_SYSTEM_WORKSPACE_ROOT at a copy of the frozen fixture, whose
    # own holdings always include a _Checking account) so this plan's
    # synthetic Positions section drives balances instead of being
    # overridden by an unrelated client_holdings.csv on disk.
    (tmp_path / "input").mkdir()
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    c = _parse(
        HEADER
        + "Other Assets,Cash,value,\"$25,000\",USD,\n"
        + "Positions,Joint_Brokerage,CASH,500000,,\n"
    )
    warnings = c.get("config_contract_warnings", [])
    assert any("25,000" in w and "Investment Holdings" in w for w in warnings), warnings


def test_parse_client_does_not_warn_with_a_checking_holdings_account(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    c = _parse(
        HEADER
        + "Other Assets,Cash,value,\"$25,000\",USD,\n"
        + "Positions,Joint_Checking,CASH,500000,,\n"
    )
    assert c.get("config_contract_warnings", []) == []
    assert c["cash_other"] == 500000
