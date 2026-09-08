"""Finding SEC-4 (system review 2026-09-07, Wave 6 item W6-2):
src.server.security_audit._summarize_csv_row_changes feeds the on-disk
admin_config_change_log.json with zero redaction, unlike _audit()'s own
write path -- a DOB/balance/SSN/merchant field edited via the admin CSV
editor stored its real before/after value in plain text.
"""
from src.server import security_audit


def test_a_dob_field_change_is_redacted_in_the_change_summary():
    before_rows = [["Household", "Personal", "DOB", "1975-01-01"]]
    after_rows = [["Household", "Personal", "DOB", "1976-02-02"]]
    changes, count = security_audit._summarize_csv_row_changes(before_rows, after_rows)
    assert count == 1
    change = changes[0]
    assert "1975-01-01" not in change["before"]
    assert "1976-02-02" not in change["after"]


def test_a_balance_field_change_is_redacted_in_the_change_summary():
    before_rows = [["Assets", "Brokerage", "Balance", "250000"]]
    after_rows = [["Assets", "Brokerage", "Balance", "260000"]]
    changes, count = security_audit._summarize_csv_row_changes(before_rows, after_rows)
    assert count == 1
    change = changes[0]
    assert "250000" not in change["before"]
    assert "260000" not in change["after"]


def test_a_non_sensitive_field_change_is_not_redacted():
    before_rows = [["Model Constants", "Monte Carlo", "mc_engine_mode", "quick_vectorized"]]
    after_rows = [["Model Constants", "Monte Carlo", "mc_engine_mode", "advanced_exact_scalar"]]
    changes, count = security_audit._summarize_csv_row_changes(before_rows, after_rows)
    assert count == 1
    change = changes[0]
    assert change["before"] == "quick_vectorized"
    assert change["after"] == "advanced_exact_scalar"
