"""Cash inside an Investment-role account never counts as household spending or income (cash plan 4.6, phase 6)."""
from src import active_plan, spending_tracker as st

COLS = ("Date", "Merchant", "Category", "Account", "Amount")


def _ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all([
            {"Account": "IRA Brokerage", "Role": "Investment"}, {"Account": "Checking", "Role": "Cash / spending"}])
        store.dataset("ytd_transactions").replace_all([
            dict(zip(COLS, ("2026-03-01", "Wire fee", "Financial Fees", "IRA Brokerage", "-25"))),
            dict(zip(COLS, ("2026-03-02", "Misc", "Other Income", "IRA Brokerage", "40"))),
            dict(zip(COLS, ("2026-03-03", "Bank fee", "Financial Fees", "Checking", "-12")))])
    return tmp_path


def test_investment_account_rows_are_transfers_and_checking_rows_still_count(tmp_path):
    root = _ws(tmp_path)
    rows = st.load_transactions_extended(root, 2026)
    classes = {t["account"]: st._shared_ytd_class(t) for t in rows}
    assert classes["IRA Brokerage"] == "transfer"
    assert classes["Checking"] != "transfer"
