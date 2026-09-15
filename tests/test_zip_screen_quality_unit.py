"""NSS scoring: percentile scaling, weighting, and coverage renormalization."""
from __future__ import annotations

import pytest

from src.housing.zip_screen.quality import score_zip
from src.housing.zip_screen.schema import NSS_WEIGHTS, ZipRecord
from src.housing.zip_screen.table import clear_cache, load_table

pytestmark = pytest.mark.unit

FIXTURE = 'tests/fixtures/zip_metrics_sample.csv'


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _full(**overrides) -> ZipRecord:
    """A record with every percentile present at 0.5 unless overridden."""
    base = dict(
        zcta='00001', state='Illinois', lat=0.0, lon=0.0,
        pctl_owner_occupied=0.5, pctl_poverty=0.5, pctl_non_student_poverty=0.5,
        pctl_tenure=0.5, pctl_tenure_nonstudent=0.5, pctl_vacancy_deviation=0.5,
        pctl_eviction_execution=0.5, pctl_eviction_filing=0.5, pctl_median_income=0.5,
    )
    base.update(overrides)
    return ZipRecord(**base)


def test_all_metrics_at_the_median_score_fifty():
    assert score_zip(_full()).score == pytest.approx(50.0)


def test_full_coverage_reports_one_hundred_percent():
    assert score_zip(_full()).coverage_pct == pytest.approx(100.0)


def test_higher_is_better_metric_uses_the_percentile_directly():
    # owner_occupied at the 90th percentile contributes 90 * its weight.
    res = score_zip(_full(pctl_owner_occupied=0.9))
    assert res.components['owner_occupied'] == pytest.approx(90.0)


def test_lower_is_better_metric_is_inverted_per_pdf_section_2_2():
    # poverty at the 90th percentile (very poor) scores 100 * (1 - 0.9) = 10.
    res = score_zip(_full(pctl_poverty=0.9))
    assert res.components['poverty'] == pytest.approx(10.0)


def test_score_is_the_weighted_sum_of_components():
    res = score_zip(_full(pctl_owner_occupied=0.9, pctl_poverty=0.1))
    expected = sum(res.components[k] * NSS_WEIGHTS[k] for k in NSS_WEIGHTS) / 100.0
    assert res.score == pytest.approx(expected)


def test_missing_metric_renormalizes_rather_than_zero_filling():
    # Dropping eviction_filing (9.0909 of weight) from an all-median record must
    # leave the score at 50, not drag it toward 45.5.
    res = score_zip(_full(pctl_eviction_filing=None))
    assert res.score == pytest.approx(50.0)
    assert 'eviction_filing' not in res.components


def test_missing_metric_reduces_reported_coverage():
    res = score_zip(_full(pctl_eviction_filing=None))
    assert res.coverage_pct == pytest.approx(100.0 - NSS_WEIGHTS['eviction_filing'])


def test_a_zip_missing_eviction_scores_like_one_at_its_weighted_mean():
    # The renormalization guarantee, stated as the spec states it.
    missing = score_zip(_full(pctl_eviction_filing=None, pctl_eviction_execution=None))
    present = score_zip(_full())
    assert missing.score == pytest.approx(present.score)


def test_no_metrics_at_all_scores_zero_with_zero_coverage():
    bare = ZipRecord(zcta='00002', state='Illinois', lat=0.0, lon=0.0)
    res = score_zip(bare)
    assert res.score == pytest.approx(0.0)
    assert res.coverage_pct == pytest.approx(0.0)


def test_band_is_attached():
    assert score_zip(_full(
        pctl_owner_occupied=0.99, pctl_poverty=0.01, pctl_tenure=0.99,
        pctl_vacancy_deviation=0.01, pctl_eviction_execution=0.01,
        pctl_eviction_filing=0.01, pctl_median_income=0.99,
    )).band == 'Exceptional'


def test_hinsdale_fixture_lands_in_a_high_band():
    # Fixture percentiles mirror the PDF's 60521 profile; its Stability
    # component there was 89.7, so NSS must land Very Favorable or better.
    res = score_zip(load_table(FIXTURE)['60521'])
    assert res.score >= 80.0
    assert res.band in ('Very Favorable', 'Exceptional')


def test_high_poverty_chicago_fixture_lands_low():
    res = score_zip(load_table(FIXTURE)['60623'])
    assert res.score < 50.0
    assert res.band == 'Relatively Unfavorable'
