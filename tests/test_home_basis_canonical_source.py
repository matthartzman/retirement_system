from pathlib import Path

from _decomp_dashboard import dashboard_js_text
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_scenario_ui_shows_canonical_home_basis_and_removes_retired_duplicates():
    js = dashboard_js_text()

    assert "function rowIsRetiredScenarioHomeDuplicate" in js
    assert "rowIsCanonicalHomeBasis" in js
    assert '(lbl.startsWith("home_sale_") || lbl === "home_basis")' in js
    assert "rowIsRetiredScenarioHomeDuplicate(r)" in js
    assert "function homeSaleScenarioYearRow" in js
    assert "shared canonical Home asset facts" in js
