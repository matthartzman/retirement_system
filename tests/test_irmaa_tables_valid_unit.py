"""Tests for IRMAA tier table sanity (Task B0, §9.5).

Guards against a recurrence of the broken MFS table, where MFJ tier3-5
rows leaked into MFS via a generic MFJ-fallback lookup, producing
non-monotonic thresholds (106k, 403k, 335k, 402k, 750k).
"""
import pytest

from src import taxes as _td


def test_every_filing_status_has_increasing_thresholds():
    for filing, tiers in _td.IRMAA_TIERS_BASE_YEAR.items():
        thr = [t[0] for t in tiers]
        assert thr == sorted(set(thr)), (filing, thr)


def test_mfs_has_the_two_statutory_tiers():
    assert len(_td.IRMAA_TIERS_BASE_YEAR["MFS"]) == 2


def test_validator_raises_on_non_monotonic_thresholds():
    """Exercise the validator logic directly on bad data, without reimporting
    the module (which would just re-run the already-fixed real dataset)."""
    bad = {"MFS": [(106000, 1.0, 1.0), (403000, 1.0, 1.0), (335000, 1.0, 1.0)]}
    with pytest.raises(ValueError, match="MFS"):
        _td._check_irmaa_tiers_monotonic(bad)


def test_validator_passes_on_good_data():
    good = {
        "MFS": [(106000, 1.0, 1.0), (403000, 1.0, 1.0)],
        "MFJ": [(212000, 1.0, 1.0), (268000, 1.0, 1.0)],
    }
    # Should not raise.
    _td._check_irmaa_tiers_monotonic(good)
