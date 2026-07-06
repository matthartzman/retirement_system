from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_ira_conversion_outflows_are_reported_separately_from_cash_withdrawals():
    from src.data_io import load_csv, parse_client
    from src.planning_engines import project

    cfg = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    rows = project(cfg)
    wife_opening = float(rows[0]["_account_opening"].get("Wife_IRA", 0.0) or 0.0)
    wife_conversion = sum(float(r.get("w_ira_conversion", 0.0) or 0.0) for r in rows)
    wife_cash = sum(float(r.get("w_ira_total_wd", 0.0) or 0.0) for r in rows)
    wife_outflow = sum(float(r.get("w_ira_total_outflow", 0.0) or 0.0) for r in rows)

    # The wife/member-2 IRA is mostly depleted by Roth conversions. The account
    # review columns must therefore include conversions; cash withdrawals alone
    # can legitimately be much lower than the opening balance.
    assert wife_conversion > wife_opening
    assert wife_outflow >= wife_conversion + wife_cash - 1.0


def test_cashflow_workbook_shows_ira_conversions_but_keeps_cash_draw_total_separate():
    # Column labels are nickname-parameterized ({_n1}/{_n2} f-strings), so
    # assert the label suffixes for both members' conversion/outflow columns.
    sheet = read("src/reporting/sheets_projection.py")
    assert "{_n1} IRA Conv'" in sheet
    assert "{_n2} IRA Conv'" in sheet
    assert "{_n1} IRA Outflow'" in sheet
    assert "{_n2} IRA Outflow'" in sheet
    assert "Σ Cash Draws" in sheet
    assert "Roth conversions are account outflows/taxable" in sheet


def test_rmd_audit_includes_conversion_outflow_columns():
    stress = read("src/reporting/sheets_stress.py")
    assert "{_a1} IRA Conversion'" in stress
    assert "{_a2} IRA Conversion'" in stress
    assert "Total IRA Cash Drawn" in stress
    assert "Total IRA Outflow" in stress
