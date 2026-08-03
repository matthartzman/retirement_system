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


BANNED_REAL_NAMES = ["redmane", "hensley", "cubs tickets", "gifts - family 12"]


def _demo_applied_files() -> list[str]:
    """Exactly the files Open Demo Plan writes -- see plan_routes._demo_plan_feature_service."""
    from src.local_plan_data_sync import PLAN_DATA_CSV_FILES, YTD_PLAN_DATA_FILES
    from src.server_services.demo_plan_service import TEXT_BACKUP_FILES

    return [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES, *TEXT_BACKUP_FILES]


def test_demo_carries_no_real_vendor_or_personal_category_names():
    """Auto-added categories and merchant aliases name real counterparties."""
    hits = []
    for p in sorted(DEMO.glob("*.csv")):
        text = p.read_text(encoding="utf-8-sig").lower()
        hits += [f"{p.name}: {b}" for b in BANNED_REAL_NAMES if b in text]
    assert not hits, f"demo data still names real counterparties: {hits}"


def test_every_demo_fixture_is_actually_applied_by_open_demo_plan():
    """A fixture in input/demo/ that nothing applies is worse than missing: it
    reads as covered while the advisor's real file stays live for the whole
    demo. client_spending_rules.csv sat here fictionalized-but-dead, which is
    why the real "Cubs Tickets"/"Gifts - Family 12" rules survived a demo."""
    applied = set(_demo_applied_files())
    dead = sorted(p.name for p in DEMO.glob("*.csv") if p.name not in applied)
    assert not dead, (
        f"input/demo/ ships fixture(s) Open Demo Plan never applies: {dead}. Add them to "
        "PLAN_DATA_CSV_FILES or demo_plan_service.TEXT_BACKUP_FILES, or delete them -- a "
        "fixture nobody applies gives false confidence that the demo covers that file."
    )


def test_live_files_the_demo_does_not_replace_carry_no_real_names():
    """The inverse of the coverage check. Whatever Open Demo Plan does not
    swap stays on screen during the demo, so any live input/*.csv left in
    place must be free of the advisor's own counterparty names."""
    applied = set(_demo_applied_files())
    hits = []
    for p in sorted(LIVE.glob("*.csv")):
        if p.name in applied:
            continue
        text = p.read_text(encoding="utf-8-sig").lower()
        hits += [f"{p.name}: {b}" for b in BANNED_REAL_NAMES if b in text]
    assert not hits, (
        f"live file(s) the demo never replaces still name real counterparties: {hits}. "
        "Either add the file to the demo swap with a fictional input/demo/ counterpart, "
        "or the demo will keep showing these on the spending screens."
    )


def test_demo_covers_every_file_open_demo_plan_applies():
    """A plan-data file with no input/demo/ counterpart is silently skipped by
    DemoPlanService.open_demo_payload(), leaving the advisor's real file in
    place for the whole demo -- how target_allocation.csv (real target weights)
    and asset_class_optimizer_controls.csv (real optimizer choices) stayed
    visible while every other screen showed the fictional household."""
    from src.local_plan_data_sync import PLAN_DATA_CSV_FILES, YTD_PLAN_DATA_FILES
    from src.server_services.demo_plan_service import TEXT_BACKUP_FILES

    missing = [
        name
        for name in [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES, *TEXT_BACKUP_FILES]
        if not (DEMO / name).exists()
    ]
    assert not missing, (
        f"input/demo/ has no fixture for {missing}; Open Demo Plan skips those files, "
        "so the advisor's real data stays live for the duration of the demo."
    )


def _budget_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_no_budget_line_label_is_shared_with_the_live_plan():
    """Budget *line* labels are free text the advisor types -- real children's
    first names and personal notes ("10k for each child in 2026") lived here."""
    def line_labels(p):
        # line_mode=summary rows are the app's own auto-synced roll-ups.
        return {
            (r.get("label") or "").strip()
            for r in _budget_rows(p)
            if (r.get("kind") or "").strip().lower() == "line"
            and (r.get("line_mode") or "").strip().lower() != "summary"
            and (r.get("label") or "").strip()
        }

    demo = line_labels(DEMO / "client_spending_budget.csv")
    live = line_labels(LIVE / "client_spending_budget.csv")
    assert demo, "demo budget has no line rows"
    # A line the app seeded from a category carries that category's own display
    # name, so those coinciding is shared taxonomy, not leaked data. Anything
    # else in a line label was typed by hand.
    taxonomy_names = set()
    with (LIVE / "client_spending_taxonomy.csv").open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("display_name") or row.get("label") or "").strip()
            if name:
                taxonomy_names.add(name)
    shared = (demo & live) - taxonomy_names
    assert not shared, (
        f"demo budget lines reuse the live plan's labels: {sorted(shared)}. These are "
        "hand-typed by the advisor and routinely name real people."
    )


def test_demo_ytd_accounts_share_no_name_with_the_live_plan():
    """Account names in ytd_account_setup.csv are the advisor's own bank and
    card names; not one may survive into the demo."""
    def accounts(p):
        if not p.exists():
            return set()
        with p.open(newline="", encoding="utf-8-sig") as f:
            return {(r.get("Account") or "").strip() for r in csv.DictReader(f) if (r.get("Account") or "").strip()}

    demo = accounts(DEMO / "ytd_account_setup.csv")
    live = accounts(LIVE / "ytd_account_setup.csv")
    assert demo, "demo ytd_account_setup.csv has no accounts"
    # "Health Savings Account (HSA)" is the app's own generic label for the HSA
    # role, not a name the advisor chose.
    shared = (demo & live) - {"Health Savings Account (HSA)"}
    assert not shared, f"demo YTD accounts copy the live plan's account names: {sorted(shared)}"


def _target_allocation(base: Path) -> dict:
    p = base / "target_allocation.csv"
    if not p.exists():
        return {}
    with p.open(newline="", encoding="utf-8-sig") as f:
        return {
            (r.get("asset_class") or "").strip(): (r.get("target_pct") or "").strip()
            for r in csv.DictReader(f)
            if (r.get("asset_class") or "").strip()
        }


def test_demo_target_allocation_is_not_the_live_plans():
    """The target weights are the advisor's own portfolio policy, not a
    statutory constant -- the demo needs its own."""
    demo, live = _target_allocation(DEMO), _target_allocation(LIVE)
    assert demo, "input/demo/target_allocation.csv is missing or empty"
    assert demo != live, "demo target_allocation.csv is a copy of the live plan's target weights"


def test_demo_target_allocation_matches_the_demo_allocation_policy():
    """target_allocation.csv and client_policy.csv's Asset Allocation Policy
    are separate inputs read by different code paths; if the demo's two copies
    disagree, the demo shows contradictory target weights."""
    policy = {
        sub: val
        for (sec, sub, lab), val in _all_sectioned(DEMO).items()
        if sec == "Asset Allocation Policy" and lab == "target_pct"
    }
    targets = _target_allocation(DEMO)
    assert policy, "demo client_policy.csv has no Asset Allocation Policy target_pct rows"
    mismatched = {k: (targets.get(k), v) for k, v in policy.items() if targets.get(k) != v}
    assert not mismatched, f"demo target_allocation.csv disagrees with the demo policy: {mismatched}"
    assert sum(int(v.rstrip("%")) for v in targets.values()) == 100


def test_demo_budget_recovery_seed_is_fictional():
    """spending_tracker.load_unified_budget() merges this seed into the budget
    whenever the category rows total zero. If the demo does not ship (and
    apply) its own, that merge pulls the advisor's real annualized actuals
    into the demo household's budget."""
    seed = DEMO / "client_spending_budget.recovery_seed.csv"
    assert seed.exists(), "input/demo/client_spending_budget.recovery_seed.csv is missing"
    demo_rows = {(r.get("kind"), r.get("key"), r.get("label"), r.get("annual_budget")) for r in _budget_rows(seed)}
    live_rows = {
        (r.get("kind"), r.get("key"), r.get("label"), r.get("annual_budget"))
        for r in _budget_rows(LIVE / "client_spending_budget.recovery_seed.csv")
    }
    shared = {row for row in demo_rows & live_rows if (row[3] or "").strip() not in ("", "0")}
    assert not shared, f"demo recovery seed carries the live plan's amounts: {sorted(shared)[:3]}"


def test_demo_disables_ytd_blend():
    """Real ytd_transactions.csv is NOT swapped by demo mode, so blending it in
    would mix the advisor's actual tracked spending into the demo projection."""
    val = _all_sectioned(DEMO).get(("Cashflow", "Spending", "ytd_blend_enabled"))
    assert (val or "").strip().upper() == "FALSE", (
        f"demo ytd_blend_enabled is {val!r}; must be FALSE so the demo cannot "
        "blend in real year-to-date transactions"
    )


def test_demo_slot_is_not_the_fixture_directory():
    """The persistent demo slot (local_state/demo_plan/, see
    demo_plan_service.DEMO_SLOT_DIR) must never resolve to input/demo/. Every
    test above reads DEMO directly and assumes it is the pristine, checked-in
    seed -- if the slot and the fixture directory ever collapsed into one, a
    captured demo edit could silently start satisfying (or breaking) these
    checks instead of the shipped fixtures they exist to guard."""
    from src.server_services.demo_plan_service import DEMO_SLOT_DIR

    assert DEMO_SLOT_DIR != "demo"
    assert (ROOT / "local_state" / DEMO_SLOT_DIR).resolve() != DEMO.resolve()
