"""PDF section 5: the University Presence Index adjustment."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import UPI_THRESHOLD, ZipRecord
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _rec(upi: float) -> ZipRecord:
    """Raw poverty is punishing (0.91); non-student poverty is mild (0.34).
    Raw tenure is punishing (0.14); non-student tenure is healthy (0.62)."""
    return ZipRecord(
        zcta='60115', state='Illinois', lat=41.93, lon=-88.75, upi=upi,
        pctl_owner_occupied=0.21, pctl_poverty=0.91, pctl_non_student_poverty=0.34,
        pctl_tenure=0.14, pctl_tenure_nonstudent=0.62, pctl_vacancy_deviation=0.71,
        pctl_eviction_execution=0.68, pctl_eviction_filing=0.74, pctl_median_income=0.18,
    )


def test_below_threshold_uses_raw_poverty_and_tenure():
    res = score_zip(_rec(upi=0.05))
    assert res.upi_adjusted is False
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.91))
    assert res.components['tenure'] == pytest.approx(100.0 * 0.14)


def test_above_threshold_substitutes_the_non_student_metrics():
    res = score_zip(_rec(upi=0.38))
    assert res.upi_adjusted is True
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.34))
    assert res.components['tenure'] == pytest.approx(100.0 * 0.62)


def test_threshold_is_exclusive_at_exactly_fifteen_percent():
    assert score_zip(_rec(upi=UPI_THRESHOLD)).upi_adjusted is False
    assert score_zip(_rec(upi=UPI_THRESHOLD + 0.001)).upi_adjusted is True


def test_adjustment_raises_the_score_materially():
    # The PDF's 60115 case: the correction is large and upward.
    raw = score_zip(_rec(upi=0.05)).score
    adjusted = score_zip(_rec(upi=0.38)).score
    assert adjusted > raw + 10.0


def test_dekalb_fixture_is_adjusted_out_of_the_bottom_band():
    res = score_zip(load_table(FIXTURE)['60115'])
    assert res.upi_adjusted is True
    assert res.score > 40.0


def test_adjustment_falls_back_to_raw_when_non_student_data_is_absent():
    rec = ZipRecord(
        zcta='00003', state='Illinois', lat=0.0, lon=0.0, upi=0.40,
        pctl_poverty=0.91, pctl_non_student_poverty=None,
        pctl_tenure=0.14, pctl_tenure_nonstudent=None,
        pctl_owner_occupied=0.5, pctl_vacancy_deviation=0.5,
        pctl_eviction_execution=0.5, pctl_eviction_filing=0.5, pctl_median_income=0.5,
    )
    res = score_zip(rec)
    assert res.components['poverty'] == pytest.approx(100.0 * (1 - 0.91))
    assert res.upi_adjusted is False
