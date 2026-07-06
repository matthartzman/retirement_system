from __future__ import annotations

from datetime import date
from pathlib import Path

from src.import_preview import preview_holdings_import, preview_ytd_transactions_import


YTD_HEADER = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"


def test_ytd_transactions_preview_is_side_effect_free_and_reports_import_risks(tmp_path: Path):
    (tmp_path / "ytd_transactions.csv").write_text(
        YTD_HEADER + "2026-01-10,Store,Groceries,Checking,,, -12.00,,Household\n",
        encoding="utf-8",
    )
    (tmp_path / "spending_category_map.csv").write_text(
        "super_group,group,category,tracking\nExpenses,Food,Groceries,core\n",
        encoding="utf-8",
    )
    incoming = (
        YTD_HEADER
        + "2026-01-10,Store,Groceries,Checking,,, -12.00,,Household\n"
        + "2026-02-01,Special Shop,New Category,New Card,,, -25.50,,Household\n"
        + "2025-12-31,Old Store,Groceries,Checking,,, -10.00,,Household\n"
    )

    preview = preview_ytd_transactions_import(tmp_path, incoming, mode="replace", today=date(2026, 6, 26))

    assert preview["success"] is True
    assert preview["schema"] == "import_preview_v1"
    assert preview["will_write"] is False
    assert preview["received"] == 3
    # All rows with a valid date are importable regardless of calendar year —
    # the app retains full transaction history for the Last Year/YTD toggle.
    assert preview["valid_current_year_rows"] == 3
    assert preview["rows_replaced"] == 1
    assert preview["skipped_not_current_year"] == 0
    assert preview["duplicate_candidates"]["matching_existing_rows"] == 1
    assert preview["unmapped_categories"] == ["New Category"]
    assert preview["account_summary"]["new_accounts"] == ["New Card"]
    assert (tmp_path / "ytd_import_history.csv").exists() is False


def test_holdings_preview_reports_counts_duplicates_dates_and_quality_flags(tmp_path: Path):
    (tmp_path / "reference_data").mkdir()
    (tmp_path / "reference_data" / "security_master.csv").write_text("symbol\nVTI\n", encoding="utf-8")
    current = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\nIRA,VTI,2026-01-01,10,100,buy,\n"
    incoming = (
        "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
        "IRA,VTI,2026-01-01,10,100,buy,\n"
        "Roth,NEWFUND,02/15/2026,5,50,buy,\n"
        ",CASH,bad-date,abc,1,cash,\n"
    )

    preview = preview_holdings_import(current, incoming, project_root=tmp_path, mode="replace")

    assert preview["success"] is True
    assert preview["schema"] == "import_preview_v1"
    assert preview["kind"] == "holdings"
    assert preview["will_write"] is False
    assert preview["received"] == 3
    assert preview["rows_replaced"] == 1
    assert preview["total_after"] == 3
    assert preview["duplicate_candidates"]["matching_existing_rows"] == 1
    assert preview["date_range"] == {"earliest": "2026-01-01", "latest": "2026-02-15"}
    assert preview["account_summary"]["new_accounts"] == ["Roth"]
    assert preview["symbol_summary"]["symbols_not_in_security_master"] == ["NEWFUND"]
    assert preview["data_quality"]["missing_account_rows"] == 1
    assert preview["data_quality"]["invalid_share_rows"] == 1
    assert preview["data_quality"]["unparseable_date_rows"] == 1
