"""Unit tests for the module-level helpers hoisted out of build_sheet4 in
src/reporting/sheets_summary.py (see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md
Phase 2a). Before this hoist these were nested closures inside a ~1,400-line
function and could not be tested in isolation.
"""
from __future__ import annotations

from src.reporting.sheets_summary import (
    ASSET_ALLOCATION_BUCKET_MAP,
    _after_status_for_total_mix,
    _candidate_symbols,
    _hide_zero_before_after_row,
    _status_for_bucket,
)


def test_asset_allocation_bucket_map_covers_expected_symbols():
    assert ASSET_ALLOCATION_BUCKET_MAP["VOO"] == "US Large Cap"
    assert ASSET_ALLOCATION_BUCKET_MAP["BND"] == "Bonds"
    assert ASSET_ALLOCATION_BUCKET_MAP["VNQ"] == "REITs"
    assert ASSET_ALLOCATION_BUCKET_MAP["CASH"] == "Cash"


def test_candidate_symbols_deduplicates_across_buckets():
    result = _candidate_symbols("Bonds", "Short-Term Bonds")
    assert result == list(dict.fromkeys(result))  # no duplicates
    assert "BND" in result


def test_candidate_symbols_unknown_bucket_returns_empty():
    assert _candidate_symbols("Not A Real Bucket") == []


def test_candidate_symbols_no_buckets_returns_empty():
    assert _candidate_symbols() == []


def test_hide_zero_before_after_row_both_under_threshold():
    assert _hide_zero_before_after_row(0.0, 0.49) is True
    assert _hide_zero_before_after_row(-0.49, 0.0) is True


def test_hide_zero_before_after_row_one_over_threshold():
    assert _hide_zero_before_after_row(0.50, 0.0) is False
    assert _hide_zero_before_after_row(0.0, 100.0) is False


def test_hide_zero_before_after_row_none_values_treated_as_zero():
    assert _hide_zero_before_after_row(None, None) is True


def test_hide_zero_before_after_row_non_numeric_is_false():
    assert _hide_zero_before_after_row("not a number", 0.0) is False


def test_status_for_bucket_fixed_income_covered_short_circuits():
    # "Bonds" is a fixed-income class; when coverage already satisfies the
    # target, the bucket is reported covered regardless of pct/tgt.
    result = _status_for_bucket("Bonds", pct=0.0, tgt=0.20, fi_covered_full=True, re_covered_full=False)
    assert result == "✓ Covered by fixed-income coverage"


def test_status_for_bucket_real_estate_covered_short_circuits():
    result = _status_for_bucket("REITs", pct=0.0, tgt=0.05, fi_covered_full=False, re_covered_full=True)
    assert result == "✓ Covered by real-estate coverage"


def test_status_for_bucket_no_target_is_blank():
    assert _status_for_bucket("US Large Cap", pct=0.30, tgt=0.0, fi_covered_full=False, re_covered_full=False) == ""


def test_status_for_bucket_within_tolerance_is_check():
    assert _status_for_bucket("US Large Cap", pct=0.30, tgt=0.31, fi_covered_full=False, re_covered_full=False) == "✓"


def test_status_for_bucket_over_target():
    result = _status_for_bucket("US Large Cap", pct=0.40, tgt=0.30, fi_covered_full=False, re_covered_full=False)
    assert result == "Over 10.0%"


def test_status_for_bucket_under_target():
    result = _status_for_bucket("US Large Cap", pct=0.20, tgt=0.30, fi_covered_full=False, re_covered_full=False)
    assert result == "Under 10.0%"


def test_after_status_for_total_mix_non_liquid_covered():
    result = _after_status_for_total_mix(
        "Fixed Income Coverage", "Non-liquid", after_pct=0.0, tgt=0.15,
        fi_covered_full=True, re_covered_full=False,
    )
    assert result == "✓ Covered"


def test_after_status_for_total_mix_non_liquid_no_target_shown_for_context():
    result = _after_status_for_total_mix(
        "Home Equity (shown, not counted toward REIT target)", "Non-liquid", after_pct=0.0, tgt=0.0,
        fi_covered_full=False, re_covered_full=False,
    )
    assert result == "Shown for context; no liquid target"


def test_after_status_for_total_mix_liquid_delegates_to_status_for_bucket():
    result = _after_status_for_total_mix(
        "US Large Cap", "Liquid", after_pct=0.30, tgt=0.31,
        fi_covered_full=False, re_covered_full=False,
    )
    assert result == "✓"
