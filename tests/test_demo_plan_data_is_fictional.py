"""The demo plan must never contain the advisor's real plan data.

`input/demo/*.csv` is applied by Open Demo Plan and is meant to be shown to
prospects and colleagues. It was originally produced by copying the live plan
and swapping only the two first names, which left every real date of birth,
Social Security estimate, annuity contract, holding lot, account balance, note
receivable, property value, budget amount, and vendor name intact.

These tests compare the demo files against the live `input/*.csv` and fail if
the household-specific figures ever coincide again -- which is exactly what a
future "just refresh the demo from my current plan" shortcut would produce.

Deliberately NOT flagged, because sharing them is correct:
  * statutory constants everyone shares (Medicare premiums, HSA/401k limits,
    SS wage base, federal/Illinois estate exemptions, gift exclusion);
  * the residence state -- Illinois is the only state the engine models an
    estate tax for, so the demo keeps it to exercise the estate sheets;
  * the pre-seeded sample modules (Acme Holdings, Grandchild_A 529, ISO/RSU
    grants, special-needs, P&C) that are already fictional in the live plan.
"""
import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "input" / "demo"
LIVE = ROOT / "input"

# (section, subsection-or-None, label) triples that identify a specific
# household. If the demo and the live plan agree on any of these, the demo is
# carrying real data.
SENSITIVE = [
    ("Household", "", "member_1_dob"),
    ("Household", "", "member_2_dob"),
    ("Household", "", "member_1_retirement_date"),
    ("Household", "", "member_2_retirement_date"),
    ("Cashflow", "Earned Income", "annual_earned_income"),
    ("Cashflow", "S-Corp", "reasonable_salary_annual"),
    ("Cashflow", "Spending", "annual_spending_base_year"),
    ("Cashflow", "Mortgage", "balance_as_of_plan_start"),
    ("Cashflow", "Mortgage", "monthly_payment"),
    ("Cashflow", "Mortgage", "annual_real_estate_taxes"),
    ("Other Assets", "Home", "value_as_of_plan_start"),
    ("Other Assets", "Home", "home_basis"),
    ("Note Receivable", "Note 1", "name"),
    ("Note Receivable", "Note 1", "face_value"),
    ("Income Streams", "Member 1 Joint Annuity", "base"),
    ("Income Streams", "Member 1 Single Annuity", "base"),
    ("Income Streams", "Member 2 Joint Annuity", "base"),
    ("Income Streams", "Member 2 Single Annuity", "base"),
    ("Income Streams", "Member 1 Joint Annuity", "first_payment"),
    ("Income Streams", "Member 2 Joint Annuity", "first_payment"),
    ("Social Security", "Member 1", "ss_benefit_age_70"),
    ("Social Security", "Member 2", "ss_benefit_age_70"),
]


def _sectioned(path: Path) -> dict:
    """Parse a sectioned client_*.csv into {(section, subsection, label): value}."""
    out = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sec = (row.get("section") or "").strip()
            sub = (row.get("subsection") or "").strip()
            lab = (row.get("label") or "").strip()
            val = (row.get("value") or "").strip()
            if sec and lab and not sec.startswith("#"):
                out[(sec, sub, lab)] = val
    return out


def _all_sectioned(base: Path) -> dict:
    merged = {}
    for p in sorted(base.glob("client_*.csv")):
        merged.update(_sectioned(p))
    return merged


def test_demo_directory_exists():
    assert DEMO.is_dir(), "input/demo/ is missing"
    assert (DEMO / "client_holdings.csv").exists()


@pytest.mark.parametrize("key", SENSITIVE, ids=lambda k: f"{k[0]}|{k[1]}|{k[2]}")
def test_sensitive_field_differs_from_live_plan(key):
    demo, live = _all_sectioned(DEMO), _all_sectioned(LIVE)
    d, l = demo.get(key), live.get(key)
    if d in (None, "") or l in (None, ""):
        pytest.skip(f"{key} not present in both demo and live plan")
    assert d != l, (
        f"Demo plan field {key} matches the live plan ({d!r}). input/demo/ must "
        "never be a copy of the advisor's real data -- regenerate it with "
        "invented figures rather than copying the current plan."
    )


def test_no_holding_lot_is_shared_with_live_plan():
    """Not one (account, symbol, date, shares, price) lot may coincide."""
    def lots(p):
        if not p.exists():
            return set()
        with p.open(newline="", encoding="utf-8-sig") as f:
            return {
                (r.get("account"), r.get("symbol"), r.get("purchase_date"),
                 r.get("shares"), r.get("purchase_price"))
                for r in csv.DictReader(f) if r.get("symbol")
            }

    demo_lots = lots(DEMO / "client_holdings.csv")
    live_lots = lots(LIVE / "client_holdings.csv")
    assert demo_lots, "demo holdings file is empty"
    shared = demo_lots & live_lots
    assert not shared, f"demo holdings share {len(shared)} real lot(s): {sorted(shared)[:3]}"


def test_demo_carries_no_real_vendor_or_personal_category_names():
    """Auto-added categories and merchant aliases name real counterparties."""
    banned = ["redmane", "hensley", "cubs tickets", "gifts - family 12"]
    hits = []
    for p in sorted(DEMO.glob("*.csv")):
        text = p.read_text(encoding="utf-8-sig").lower()
        hits += [f"{p.name}: {b}" for b in banned if b in text]
    assert not hits, f"demo data still names real counterparties: {hits}"


def test_demo_disables_ytd_blend():
    """Real ytd_transactions.csv is NOT swapped by demo mode, so blending it in
    would mix the advisor's actual tracked spending into the demo projection."""
    val = _all_sectioned(DEMO).get(("Cashflow", "Spending", "ytd_blend_enabled"))
    assert (val or "").strip().upper() == "FALSE", (
        f"demo ytd_blend_enabled is {val!r}; must be FALSE so the demo cannot "
        "blend in real year-to-date transactions"
    )
