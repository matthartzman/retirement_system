"""Schema constants for the ZIP screener: weights, bands, and the record type."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.schema import (
    BANDS,
    COVERAGE_FLOOR_PCT,
    NSS_DISCLOSURE,
    NSS_WEIGHTS,
    SCORE_MODEL_VERSION,
    VACANCY_IDEAL_RATE,
    ZipRecord,
    band_for,
)

pytestmark = pytest.mark.unit


def test_nss_weights_sum_to_one_hundred():
    assert round(sum(NSS_WEIGHTS.values()), 4) == 100.0


def test_nss_weights_preserve_the_pdf_relative_ordering():
    # PDF Rev 2.1 points 8/6/5/4/4/3/3 renormalized by 100/33.
    assert NSS_WEIGHTS['owner_occupied'] > NSS_WEIGHTS['poverty'] > NSS_WEIGHTS['tenure']
    assert NSS_WEIGHTS['tenure'] > NSS_WEIGHTS['vacancy']
    assert NSS_WEIGHTS['vacancy'] == pytest.approx(NSS_WEIGHTS['eviction_execution'])
    assert NSS_WEIGHTS['eviction_filing'] == pytest.approx(NSS_WEIGHTS['median_income'])


def test_owner_occupied_weight_matches_the_renormalization():
    assert NSS_WEIGHTS['owner_occupied'] == pytest.approx(8 * 100 / 33, abs=1e-4)


def test_disclosure_string_is_verbatim():
    assert NSS_DISCLOSURE == (
        'Measures housing and economic stability. Does not measure crime or safety.'
    )


def test_constants_match_the_spec():
    assert COVERAGE_FLOOR_PCT == 70.0
    assert VACANCY_IDEAL_RATE == 0.06
    assert SCORE_MODEL_VERSION == 'nss-1.0'


@pytest.mark.parametrize('score,expected', [
    (95.0, 'Exceptional'),
    (90.0, 'Exceptional'),
    (89.9, 'Very Favorable'),
    (80.0, 'Very Favorable'),
    (75.0, 'Generally Favorable'),
    (65.0, 'Mixed'),
    (55.0, 'Below Average'),
    (49.9, 'Relatively Unfavorable'),
    (0.0, 'Relatively Unfavorable'),
])
def test_band_for_matches_pdf_section_2_4(score, expected):
    assert band_for(score) == expected


def test_bands_are_ordered_high_to_low():
    thresholds = [t for t, _ in BANDS]
    assert thresholds == sorted(thresholds, reverse=True)


def test_zip_record_defaults_missing_metrics_to_none():
    rec = ZipRecord(zcta='60521', state='Illinois', lat=41.8, lon=-87.93)
    assert rec.pctl_eviction_filing is None
    assert rec.pctl_owner_occupied is None
    assert rec.place_population == 0
