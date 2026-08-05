from src.server import app


def test_config_rows_endpoint_returns_core_spending_growth_controls():
    client = app.test_client()
    response = client.get('/api/config/rows')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    rows = payload['rows']
    labels = {r.get('label') for r in rows}
    assert 'core_spending_growth_mode' in labels
    assert 'core_spending_manual_growth_rate' in labels
    assert 'inflation_general' in labels
    assert 'spending_freeze_year' in labels
    mode = next(r for r in rows if r.get('label') == 'core_spending_growth_mode')
    assert mode.get('section') == 'Cashflow'
    assert mode.get('subsection') == 'Spending'
    assert mode.get('choice_options') == [
        {'value': 'cpi', 'label': 'Use CPI / General Inflation'},
        {'value': 'manual_override', 'label': 'Manual spending increase override'},
    ]
