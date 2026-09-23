"""Server-side rejection of impossible requests (design 2026-09-16 §8).

Also carries the three request-adapter enum-rejection tests Task 9 dropped
from tests/test_housing_optimizer_unit.py on the grounds that they assert a
contract api.py had not yet grown (see the inherited-obligation note above
Task 10 Step 1 in the design doc). The two ``test_parse_location_*``
companions from that same drop are genuinely obsolete -- ``_parse_location``
served the manual-location mode, which this design removes -- and are not
resurrected here.
"""
import pytest

from src.housing.api import validate_request

pytestmark = pytest.mark.contract


def _body(**over):
    body = {
        'objective': 'net_worth', 'search_mode': 'full',
        'move2_strategy': 'anchored', 'no_dual_ownership': True,
        'original_home': {'disposition': 'sell',
                          'earliest_sale_year': 2030, 'latest_sale_year': 2045},
        'move1': {'earliest_acquisition_year': 2031,
                  'latest_acquisition_year': 2046, 'action': 'auto',
                  'search': {'anchors': [{'kind': 'zip', 'anchor_zip': '80014'},
                                         {'kind': 'zip', 'anchor_zip': '60521'}],
                             'radius_miles': 25, 'min_quality_score': 60,
                             'area_type': 'any', 'max_population': None,
                             # shortlist_size left the request schema with the
                             # step-1 selection table (design 2026-09-19 §5.4);
                             # selected_zips replaced it.
                             'selected_zips': ['80014', '60521'],
                             'dwelling': {}}},
    }
    body.update(over)
    return body


def test_a_valid_request_passes():
    assert validate_request(_body()) is None


def test_rule1_sale_window_must_not_be_inverted():
    msg = validate_request(_body(original_home={
        'disposition': 'sell', 'earliest_sale_year': 2045, 'latest_sale_year': 2030}))
    assert 'sale year' in msg.lower()


def test_rule3_the_screenshot_case_is_rejected_before_any_search_runs():
    """Move-2 latest year 2030 against a move-1 window opening in 2031: no
    move-2 candidate can exist. v1 ran a full search and reported nothing."""
    msg = validate_request(_body(move2={
        'earliest_acquisition_year': 2029, 'latest_acquisition_year': 2030,
        'action': 'auto', 'concurrent': False, 'anchor_count': 5,
        'search': _body()['move1']['search']}))
    assert msg is not None
    assert '2031' in msg


def test_rule4_keep_plus_buy_is_rejected_under_no_dual_ownership():
    body = _body(original_home={'disposition': 'keep'})
    body['move1']['action'] = 'buy'
    msg = validate_request(body)
    assert 'owning two homes' in msg


def test_rule4_does_not_fire_under_auto_disposition():
    """Under auto the sell branch still yields candidates, so blocking the run
    would be wrong."""
    body = _body(original_home={'disposition': 'auto',
                                'earliest_sale_year': 2030, 'latest_sale_year': 2045})
    body['move1']['action'] = 'buy'
    assert validate_request(body) is None


def test_rule5_buying_before_the_sale_window_opens_is_rejected():
    body = _body(original_home={'disposition': 'sell',
                                'earliest_sale_year': 2040, 'latest_sale_year': 2045})
    body['move1'].update({'action': 'buy', 'earliest_acquisition_year': 2030,
                          'latest_acquisition_year': 2035})
    msg = validate_request(body)
    assert '2040' in msg


def test_rule6_anchor_count_must_be_between_one_and_five():
    body = _body()
    body['move1']['search']['anchors'] = []
    assert 'between 1 and 5' in validate_request(body)

    body['move1']['search']['anchors'] = [
        {'kind': 'zip', 'anchor_zip': f'8001{i}'} for i in range(6)]
    assert 'between 1 and 5' in validate_request(body)


def test_rule6_a_single_anchor_is_now_allowed():
    body = _body()
    body['move1']['search']['anchors'] = [{'kind': 'zip', 'anchor_zip': '80014'}]
    assert validate_request(body) is None


def test_rule6b_apartment_property_type_cannot_be_forced_to_buy():
    body = _body()
    body['move1']['action'] = 'buy'
    body['move1']['search']['dwelling'] = {'property_type': 'apartment'}
    msg = validate_request(body)
    assert msg is not None
    assert 'apartment' in msg.lower()


def test_rule6b_apartment_property_type_is_fine_under_rent_or_auto():
    for action in ('rent', 'auto'):
        body = _body()
        body['move1']['action'] = action
        body['move1']['search']['dwelling'] = {'property_type': 'apartment'}
        assert validate_request(body) is None, action


def test_rule6b_only_applies_to_apartment_not_other_property_types():
    body = _body()
    body['move1']['action'] = 'buy'
    body['move1']['search']['dwelling'] = {'property_type': 'condo'}
    assert validate_request(body) is None


def test_rule7_family_presence_needs_a_five_digit_zip_and_an_ordered_window():
    assert validate_request(_body(family_presence={
        'zip': '123', 'radius_miles': 25,
        'from_year': 2026, 'through_year': 2050})) is not None
    assert validate_request(_body(family_presence={
        'zip': '60521', 'radius_miles': 25,
        'from_year': 2050, 'through_year': 2026})) is not None


def test_rule8_concurrent_requires_full_search_mode():
    msg = validate_request(_body(search_mode='narrowed', move2={
        'earliest_acquisition_year': 2040, 'latest_acquisition_year': 2050,
        'action': 'auto', 'concurrent': True, 'anchor_count': 5,
        'search': _body()['move1']['search']}))
    assert 'full' in msg.lower()


def test_rule9_price_range_must_not_be_inverted():
    body = _body()
    body['move1']['search']['dwelling']['target_purchase_price_range'] = [700000, 400000]
    assert 'maximum' in validate_request(body).lower()


def test_locations_is_no_longer_accepted():
    """The manual-location mode is gone; accepting it silently would produce
    candidates with no ZIP, score or distance."""
    assert validate_request(_body(locations=[{'state': 'CO'}])) is not None


# ---------------------------------------------------------------------------
# Inherited from Task 9 (2026-09-16): enum rejections not covered by any of
# §8's numbered rules above.
# ---------------------------------------------------------------------------

def test_request_adapter_rejects_unknown_objective():
    msg = validate_request(_body(objective='not_a_real_objective'))
    assert msg is not None
    assert 'objective' in msg.lower()


def test_request_adapter_rejects_unknown_search_mode():
    msg = validate_request(_body(search_mode='not_a_real_mode'))
    assert msg is not None
    assert 'search_mode' in msg.lower()


def test_request_adapter_rejects_unknown_move2_strategy():
    msg = validate_request(_body(move2_strategy='not_a_real_strategy'))
    assert msg is not None
    assert 'move2_strategy' in msg.lower()


def test_rule10_down_payment_pct_must_be_a_fraction_between_0_and_1():
    msg = validate_request(_body(down_payment_pct=1.5))
    assert msg is not None
    assert 'down payment' in msg.lower()


def test_rule10_mortgage_rate_pct_must_be_a_fraction_between_0_and_1():
    msg = validate_request(_body(mortgage_rate_pct=-0.01))
    assert msg is not None
    assert 'mortgage rate' in msg.lower()


def test_rule10_omitted_financing_fields_are_fine():
    assert validate_request(_body()) is None
