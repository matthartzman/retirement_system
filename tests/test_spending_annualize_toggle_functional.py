"""Real estate taxes (and other lumpy, one-or-two-installment-a-year spend
categories) should not be scaled by elapsed-days-of-the-year when computing
an "annualized" figure -- a lump payment paid early in the year gets
multiplied by (365/days_so_far), wildly overstating the projected full-year
total, and understated the same way if the payment hasn't landed yet. This
matters most for spending_service.load_actuals_payload ("Load annualized
current spend" in the Budgeting UI), which writes the annualized figure
directly into the household's annual budget with no undo.

Real estate taxes are now excluded from annualization by default (see
spending_tracker._TIME_BOUNDED_CATEGORY_IDS), the same way Income/Travel/
Large Discretionary already were. This item adds a general, user-maintained
mechanism on top of that hardcoded default: a "no_annualize" toggle
persisted per category OR per group in client_spending_budget.csv (see
_resolve_no_annualize), editable from the Budgeting UI, so a household can
flag any other lumpy line item -- or un-flag one of the built-in defaults --
without a code change.
"""
from pathlib import Path

from src import spending_tracker as st


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed(root: Path, taxonomy: str, budget: str, txns: str, aliases: str = ""):
    write(root / "input/client_spending_taxonomy.csv", taxonomy)
    write(root / "input/client_spending_budget.csv", budget)
    write(root / "input/client_spending_aliases.csv",
          "match_value,match_field,exact,priority,category_id,source\n" + aliases)
    write(root / "input/ytd_transactions.csv", txns)


def _find_category(summary, cid):
    for tt in summary["tracking_types"]:
        for g in tt["groups"]:
            for c in g["categories"]:
                if c["id"] == cid:
                    return c
    return None


def _find_group(summary, tracking_type, group_name):
    for tt in summary["tracking_types"]:
        if tt["tracking_type"] != tracking_type:
            continue
        for g in tt["groups"]:
            if g["group"] == group_name:
                return g
    return None


def test_real_estate_taxes_default_to_not_annualized(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="tracking_type,group,category_id,label,origin,status,notes\nHousing,Real Estate Taxes,real_estate_taxes,Real Estate Taxes,template,active,\n",
        budget="",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-03-01,County Treasurer,Real Estate Taxes,Checking,-8000,Household\n"
        ),
        aliases="Real Estate Taxes,category,TRUE,50,real_estate_taxes,test\n",
    )
    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "real_estate_taxes")
    assert cat is not None
    assert cat["no_annualize"] is True
    assert cat["no_annualize_own_setting"] is None  # inherited default, not an explicit row
    assert cat["actual"] == 8000.0
    # The whole point: no day-based scaling applied, regardless of what
    # today happens to be when this test runs.
    assert cat["annualized_actual"] == cat["actual"]


def test_explicit_category_toggle_overrides_the_default_for_any_category(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="tracking_type,group,category_id,label,origin,status,notes\nCore Expenses,Insurance,umbrella_insurance,Umbrella Insurance,template,active,\n",
        budget="kind,key,label,annual_budget,start_year,end_year,one_time_year,notes,_mode,line_section,line_mode,no_annualize\n"
               "category,umbrella_insurance,Umbrella Insurance,,,,,,,,,TRUE\n",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-02-01,Insurer,Umbrella Insurance,Checking,-1200,Household\n"
        ),
        aliases="Umbrella Insurance,category,TRUE,50,umbrella_insurance,test\n",
    )
    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "umbrella_insurance")
    assert cat is not None
    assert cat["no_annualize"] is True
    assert cat["no_annualize_own_setting"] is True
    assert cat["annualized_actual"] == cat["actual"]


def test_explicit_false_override_turns_off_a_built_in_default(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="tracking_type,group,category_id,label,origin,status,notes\nHousing,Real Estate Taxes,real_estate_taxes,Real Estate Taxes,template,active,\n",
        budget="kind,key,label,annual_budget,start_year,end_year,one_time_year,notes,_mode,line_section,line_mode,no_annualize\n"
               "category,real_estate_taxes,Real Estate Taxes,,,,,,,,,FALSE\n",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-03-01,County Treasurer,Real Estate Taxes,Checking,-8000,Household\n"
        ),
        aliases="Real Estate Taxes,category,TRUE,50,real_estate_taxes,test\n",
    )
    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "real_estate_taxes")
    assert cat is not None
    assert cat["no_annualize"] is False
    assert cat["no_annualize_own_setting"] is False


def test_group_level_toggle_covers_every_category_in_it(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy=(
            "tracking_type,group,category_id,label,origin,status,notes\n"
            "Core Expenses,Large Gifts,wedding_gift,Wedding Gift,template,active,\n"
            "Core Expenses,Large Gifts,graduation_gift,Graduation Gift,template,active,\n"
        ),
        budget="kind,key,label,annual_budget,start_year,end_year,one_time_year,notes,_mode,line_section,line_mode,no_annualize\n"
               "group,Core Expenses::Large Gifts,Large Gifts,,,,,,,,,TRUE\n",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-02-01,Jewelers,Wedding Gift,Checking,-2000,Household\n"
            "2026-02-01,Bookstore,Graduation Gift,Checking,-300,Household\n"
        ),
        aliases=(
            "Wedding Gift,category,TRUE,50,wedding_gift,test\n"
            "Graduation Gift,category,TRUE,50,graduation_gift,test\n"
        ),
    )
    summary = st.spending_summary_taxonomy(root, year=2026)
    for cid in ("wedding_gift", "graduation_gift"):
        cat = _find_category(summary, cid)
        assert cat is not None, cid
        assert cat["no_annualize"] is True, cid
        assert cat["no_annualize_own_setting"] is None, cid  # inherited from the group
        assert cat["annualized_actual"] == cat["actual"], cid
    group = _find_group(summary, "Core Expenses", "Large Gifts")
    assert group is not None
    assert group["no_annualize_own_setting"] is True
    assert group["annualized_actual"] == group["actual"]


def test_category_override_wins_over_a_conflicting_group_setting(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="tracking_type,group,category_id,label,origin,status,notes\nCore Expenses,Large Gifts,wedding_gift,Wedding Gift,template,active,\n",
        budget="kind,key,label,annual_budget,start_year,end_year,one_time_year,notes,_mode,line_section,line_mode,no_annualize\n"
               "group,Core Expenses::Large Gifts,Large Gifts,,,,,,,,,TRUE\n"
               "category,wedding_gift,Wedding Gift,,,,,,,,,FALSE\n",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-02-01,Jewelers,Wedding Gift,Checking,-2000,Household\n"
        ),
        aliases="Wedding Gift,category,TRUE,50,wedding_gift,test\n",
    )
    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "wedding_gift")
    assert cat is not None
    assert cat["no_annualize_own_setting"] is False
    assert cat["no_annualize"] is False


def test_load_annualized_actuals_payload_reflects_the_no_annualize_toggle(tmp_path):
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    root = tmp_path
    _seed(
        root,
        taxonomy="tracking_type,group,category_id,label,origin,status,notes\nHousing,Real Estate Taxes,real_estate_taxes,Real Estate Taxes,template,active,\n",
        budget="",
        txns=(
            "Date,Merchant,Category,Account,Amount,Owner\n"
            "2026-03-01,County Treasurer,Real Estate Taxes,Checking,-8000,Household\n"
        ),
        aliases="Real Estate Taxes,category,TRUE,50,real_estate_taxes,test\n",
    )
    svc = SpendingService(SpendingServiceContext(base_dir=root))
    payload, status = svc.load_actuals_payload()
    assert status == 200
    # The exact figure "Load annualized current spend" would write into the
    # household's real_estate_taxes budget must equal the actual paid, not a
    # days-elapsed-scaled extrapolation of a single lump payment.
    assert payload["actuals"]["real_estate_taxes"] == 8000.0


def test_no_annualize_toggle_round_trips_through_the_live_ui_save_path(tmp_path):
    """The Budgeting UI reads/writes budgets via load_budget_by_category and
    save_budget_by_category (the /api/spending/budget/taxonomy[/save] route
    handlers) -- NOT via load_unified_budget/save_unified_budget directly.
    A toggle that only worked through the latter would be silently dropped
    the moment a real user flipped it in the UI.
    """
    root = tmp_path
    _seed(
        root,
        taxonomy=(
            "tracking_type,group,category_id,label,origin,status,notes\n"
            "Core Expenses,Insurance,umbrella_insurance,Umbrella Insurance,template,active,\n"
        ),
        budget="",
        txns="Date,Merchant,Category,Account,Amount,Owner\n",
        aliases="",
    )
    # Simulate the UI toggling a category on, then saving.
    st.save_budget_by_category(
        root, {"umbrella_insurance": {"annual_budget": 1200, "no_annualize": True}}
    )
    loaded = st.load_budget_by_category(root)
    assert loaded["umbrella_insurance"]["no_annualize"] == "TRUE"

    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "umbrella_insurance")
    assert cat is not None
    assert cat["no_annualize_own_setting"] is True
    assert cat["no_annualize"] is True

    # Now flip it off explicitly.
    st.save_budget_by_category(
        root, {"umbrella_insurance": {"annual_budget": 1200, "no_annualize": False}}
    )
    loaded = st.load_budget_by_category(root)
    assert loaded["umbrella_insurance"]["no_annualize"] == "FALSE"
    summary = st.spending_summary_taxonomy(root, year=2026)
    cat = _find_category(summary, "umbrella_insurance")
    assert cat["no_annualize_own_setting"] is False
    assert cat["no_annualize"] is False
