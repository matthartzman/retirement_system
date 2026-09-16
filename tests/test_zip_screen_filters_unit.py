"""Area-type and population funnel stages (design 2026-09-16 §6.2)."""
import pytest

from src.housing.zip_screen.schema import ZipRecord
from src.housing.zip_screen.screen import ScreenRequest, run_screen

pytestmark = pytest.mark.unit


def _rec(zcta, *, lat=39.7, lon=-104.9, density_pop=100000, land=10.0,
         place_pop=100000, state='Colorado'):
    """A record dense enough to clear the coverage floor on every percentile."""
    return ZipRecord(
        zcta=zcta, state=state, state_abbrev='CO', primary_place=f'Place{zcta}',
        place_population=place_pop, zcta_population=density_pop, land_area_sqmi=land,
        lat=lat, lon=lon, median_home_value=400000, state_median_home_value=400000,
        upi=0.02,
        pctl_owner_occupied=0.80, pctl_poverty=0.80, pctl_non_student_poverty=0.80,
        pctl_tenure=0.80, pctl_tenure_nonstudent=0.80, pctl_vacancy_deviation=0.80,
        pctl_eviction_execution=None, pctl_eviction_filing=None, pctl_median_income=0.80,
    )


def _table():
    # 40000/10 = 4000 ppsm -> urban;  5000/10 = 500 ppsm -> exurban
    return {
        '80001': _rec('80001', density_pop=40000, place_pop=500000),
        '80002': _rec('80002', lat=39.85, density_pop=5000, place_pop=9000),
    }


def _req(**kw):
    kw.setdefault('anchor_zip', '80001')
    kw.setdefault('radius_miles', 25)
    kw.setdefault('min_quality_score', 0)
    kw.setdefault('shortlist_size', 5)
    kw.setdefault('property_spec', {})
    kw.setdefault('area_type', 'any')
    kw.setdefault('max_population', None)
    return ScreenRequest(**kw)


def test_funnel_reports_every_stage_in_order():
    result = run_screen(_req(), table=_table())
    assert list(result.funnel) == [
        'in_radius', 'with_data', 'above_score', 'matching_area_type',
        'under_population_cap', 'affordable', 'distinct', 'near_family', 'promoted',
    ]


def test_area_type_any_filters_nothing_but_still_appears_in_the_funnel():
    result = run_screen(_req(area_type='any'), table=_table())
    assert result.funnel['matching_area_type'] == result.funnel['above_score']


def test_area_type_filters_to_the_matching_density_bucket():
    result = run_screen(_req(area_type='exurban'), table=_table())
    assert [z.zcta for z in result.shortlist] == ['80002']
    assert result.funnel['matching_area_type'] == 1


def test_population_cap_is_a_maximum_with_no_minimum():
    result = run_screen(_req(max_population=10000), table=_table())
    assert [z.zcta for z in result.shortlist] == ['80002']
    assert result.funnel['under_population_cap'] == 1


def test_no_population_cap_keeps_everything():
    result = run_screen(_req(max_population=None), table=_table())
    assert result.funnel['under_population_cap'] == result.funnel['matching_area_type']


def test_screened_zip_carries_area_type_and_population_for_display():
    z = next(z for z in run_screen(_req(), table=_table()).shortlist if z.zcta == '80002')
    assert z.area_type == 'exurban'
    assert z.population == 9000


def test_relaxation_names_the_stage_that_emptied_the_funnel():
    result = run_screen(_req(area_type='rural'), table=_table())
    assert result.shortlist == []
    assert result.relaxation['stage'] == 'matching_area_type'
    assert result.relaxation['field'] == 'area_type'


def test_relaxation_still_names_the_score_floor_when_that_is_the_cause():
    result = run_screen(_req(min_quality_score=99.9), table=_table())
    assert result.shortlist == []
    assert result.relaxation['stage'] == 'above_score'
    assert result.relaxation['field'] == 'min_quality_score'
