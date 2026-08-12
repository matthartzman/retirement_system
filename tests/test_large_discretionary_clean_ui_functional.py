from pathlib import Path
import importlib.util

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def _load_app_core_without_flask():
    import sys, types
    if 'flask' not in sys.modules:
        flask = types.ModuleType('flask')
        class Flask:
            def __init__(self, *a, **k): pass
            def route(self, *a, **k):
                def deco(f): return f
                return deco
            def errorhandler(self, *a, **k):
                def deco(f): return f
                return deco
            def before_request(self, f): return f
            def after_request(self, f): return f
        flask.Flask = Flask
        flask.g = types.SimpleNamespace()
        flask.jsonify = lambda *a, **k: {'args': a, 'kwargs': k}
        flask.make_response = lambda x=None, *a, **k: x
        flask.redirect = lambda *a, **k: None
        flask.request = types.SimpleNamespace(method='GET')
        flask.send_file = lambda *a, **k: None
        flask.send_from_directory = lambda *a, **k: None
        flask.url_for = lambda *a, **k: ''
        sys.modules['flask'] = flask
        exc = types.ModuleType('werkzeug.exceptions')
        class HTTPException(Exception):
            code = 500
            description = ''
        exc.HTTPException = HTTPException
        sys.modules['werkzeug.exceptions'] = exc
        prox = types.ModuleType('werkzeug.middleware.proxy_fix')
        class ProxyFix:
            def __init__(self, app, *a, **k): self.app = app
            def __call__(self, environ, start_response): return self.app(environ, start_response)
        prox.ProxyFix = ProxyFix
        sys.modules['werkzeug.middleware.proxy_fix'] = prox
    spec = importlib.util.spec_from_file_location('app_core_for_test', ROOT / 'src/server/app_core.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_canonical_large_discretionary_rows_are_visible_as_planned_spending():
    mod = _load_app_core_without_flask()
    rows = [
        ['section','subsection','label','value','units','notes'],
        ['Cashflow','Large Discretionary Expenses','extra_1_type','Weddings','',''],
        ['Cashflow','Large Discretionary Expenses','extra_1_amount','$100,000','USD',''],
        ['Cashflow','Large Discretionary Expenses','extra_1_year','2027','year',''],
        ['Cashflow','Large Discretionary Expenses','extra_2_type','Home Projects','',''],
        ['Cashflow','Large Discretionary Expenses','extra_2_amount','$25,000','USD',''],
        ['Cashflow','Large Discretionary Expenses','extra_2_start_year','2026','year',''],
        ['Cashflow','Large Discretionary Expenses','extra_2_end_year','2030','year',''],
    ]
    events = mod._large_discretionary_expenses_from_csv_rows(rows)
    assert [e['type'] for e in events] == ['Wedding', 'Other']
    assert events[0]['amount'] == '$100,000'
    assert events[1]['start_year'] == '2026'


def test_engine_reads_only_canonical_large_discretionary_section():
    src = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    assert "Large Discretionary Expenses" in src
    assert "Travel & Extras" not in src


def test_user_ui_uses_visible_category_select_not_vacation_only_button():
    """The Large Discretionary editor must offer a visible category dropdown.

    2026-08-11: re-pointed from renderTravelExtras to
    renderLargeDiscretionaryBudgetPage. The old "Travel & Extras" table this
    test was written against had no callers and was deleted in the dead-code
    sweep -- so these assertions were passing on source text that no user could
    reach. The guard's INTENT (a visible category select, not a vacation-only
    button) is unchanged and is satisfied by the live budget-line editor.
    """
    js = dashboard_js_text()
    # The live editor and its category dropdown.
    assert "function renderLargeDiscretionaryBudgetPage" in js
    assert '<select onchange="updateLargeDiscLine(' in js
    # The dropdown is populated from a real category list, not a single button.
    assert 'LARGE_DISC_TYPES = ["Wedding", "Large Gifts", "Other"]' in js
    assert "function largeDiscTypeFromLine" in js
    # Rows are user-addable and user-removable, not a fixed vacation-only row.
    assert "function addLargeDiscLine" in js
    assert "function deleteLargeDiscLine" in js


def test_user_ui_routes_home_sale_out_of_economic_tax_assumptions():
    js = dashboard_js_text()
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert '!rowIsHomeSaleAssumption(r)' in js
    assert 'case "scenarios":\n        return (\n          (sec === "Scenarios"' in js
    assert 'sec === "Model Constants" && sub === "home_sale"' in js
