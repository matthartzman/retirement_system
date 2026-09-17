"""GET /api/housing/zip-lookup contract: ZIP -> city/state/area_type/population,
for the Spending -> Housing page's ZIP-first location entry (design
2026-09-16-housing-financing-and-zip-ux)."""
import pytest

from src.housing.api import zip_lookup

pytestmark = pytest.mark.contract


def test_a_recognized_zip_resolves():
    payload, status = zip_lookup('60521')
    assert status == 200
    assert payload['success'] is True
    assert payload['state']
    assert payload['city']
    assert payload['area_type'] in ('urban', 'suburban', 'exurban', 'rural')
    assert payload['population'] >= 0


def test_an_unrecognized_zip_is_a_404():
    payload, status = zip_lookup('00000')
    assert status == 404
    assert payload['success'] is False
    assert 'not recognized' in payload['error'].lower()


def test_a_malformed_zip_is_a_400():
    for bad in ('123', 'abcde', '', '123456'):
        payload, status = zip_lookup(bad)
        assert status == 400, f'{bad!r} should be rejected'
        assert payload['success'] is False
