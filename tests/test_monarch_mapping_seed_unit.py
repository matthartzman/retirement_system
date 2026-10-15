"""M1b: seeding Monarch matches and policies from the user's mapping CSV."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

from src import active_plan
from src import monarch_balances_import as mbi
from src import monarch_mapping_seed as seed
from src import ytd_tracking as ytd

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)
HEADER = ["Monarch", "App Location", "App Field", "Status", "Primary Source"]
MAPPING = [
    ["Roth - Matt", "Investment Holdings", "Matt's Roth", "Active", "App"],
    ["Mortgage 1.99% 7/34", "Other Assets and Liabilities", "Primary home - Current Loan Amount", "Active", "Monarch"],
    ["Costco Anywhere Visa Card by Citi (...1530)", "", "Costco Visa", "Active", "Monarch"],
    ["Annuity - Matt - Dec 2025", "SS, Pensions, & Annuities", "Matt Single Annuity", "Active", "Monarch"],
    ["Venmo", "", "IGNORE", "Active", "App"],
    ["2016 KIA Optima EX", "Other Assets and Liabilities", "Auto - 2016 Kia Optima", "Active", "Monarch"],
    ["Not In Monarch Acct", "Investment Holdings", "Matt's Trust", "CLOSED", "App"],
]
MONARCH = ["Roth - Matt", "Mortgage 1.99% 7/34", "Costco Anywhere Visa Card by Citi (...1530)",
           "Annuity - Matt - Dec 2025", "Venmo", "2016 KIA Optima EX"]


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", [
        {"Account": "Matt's Roth", "Role": "Investment", "Mapped Investment Account": "Matt's Roth", "Current Value": "1"},
        {"Account": "Costco Visa", "Role": "Credit card", "Current Balance": "10"},
    ])
    bal = base / "Monarch Extractor" / "output" / "balances.csv"
    bal.parent.mkdir(parents=True)
    with bal.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(mbi.EXPECTED_HEADER)
        for d in ("2026-10-13", "2026-10-14"):
            for n in MONARCH:
                w.writerow([d, seed.account_key(n), n, 100.0])
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    mp = tmp_path / "mapping.csv"
    with mp.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(MAPPING)
    return base, mp


def test_policy_rules():
    p = seed.policy_for
    assert p({"App Field": "IGNORE", "Primary Source": "App"}) == "ignore"
    assert p({"App Location": "SS, Pensions, & Annuities", "App Field": "X", "Primary Source": "Monarch"}) == "app"
    assert p({"App Field": "X", "Primary Source": "Monarch"}) == "auto"
    assert p({"App Field": "X", "Primary Source": "App"}) == "app"


def test_seed_saves_resolvable_targets_keeps_pending_and_skips_unknown_accounts(tmp_path):
    base, mp = _workspace(tmp_path)
    report = seed.seed_mapping(base, mp)
    assert [r["monarch"] for r in report["not_in_monarch"]] == ["Not In Monarch Acct"]
    assert [r["monarch"] for r in report["ignored"]] == ["Venmo"]
    with active_plan.workspace_store(base) as store:
        m = store.monarch.mapping()
    assert m["roth - matt"] == {"kind": "setup_account", "ref": "Matt's Roth", "policy": "app"}
    assert m["mortgage 1.99% 7/34"] == {"kind": "plan:mortgage", "ref": "", "policy": "auto"}
    # blank location + real field is Other Assets and Liabilities, and the card is an Accounts & Sources row
    assert m["costco anywhere visa card by citi (...1530)"] == {"kind": "setup_account", "ref": "Costco Visa", "policy": "auto"}
    assert m["annuity - matt - dec 2025"]["policy"] == "app" and m["annuity - matt - dec 2025"]["kind"] == "pending"
    assert m["2016 kia optima ex"] == {"kind": "pending", "ref": "Other Assets and Liabilities|Auto - 2016 Kia Optima", "policy": "auto"}
    assert m["venmo"] == {"kind": "ignore", "ref": "", "policy": "ignore"}
    assert "not in monarch acct" not in m


def test_seed_is_idempotent_and_dry_run_writes_nothing(tmp_path):
    base, mp = _workspace(tmp_path)
    seed.seed_mapping(base, mp, dry_run=True)
    with active_plan.workspace_store(base) as store:
        assert store.monarch.mapping() == {}
    first = seed.seed_mapping(base, mp)
    second = seed.seed_mapping(base, mp)
    assert second["saved"] == [] and len(second["kept"]) == len(first["saved"]) + len(first["pending"]) + len(first["ignored"])


def test_reimport_keeps_what_the_user_changed_unless_overwrite(tmp_path):
    base, mp = _workspace(tmp_path)
    seed.seed_mapping(base, mp)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_policy("roth - matt", "auto")
    seed.seed_mapping(base, mp)
    with active_plan.workspace_store(base) as store:
        assert store.monarch.mapping()["roth - matt"]["policy"] == "auto"
    seed.seed_mapping(base, mp, overwrite=True)
    with active_plan.workspace_store(base) as store:
        assert store.monarch.mapping()["roth - matt"]["policy"] == "app"
