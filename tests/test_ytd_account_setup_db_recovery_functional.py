from pathlib import Path
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_ytd_account_setup_save_mirrors_to_sqlite_and_recovery_endpoint_exists():
    text = Path('src/server/plan_routes.py').read_text(encoding='utf-8')
    assert 'account-setup/recover' in text
    assert '_mirror_ytd_file_to_sqlite("ytd_account_setup.csv")' in text
    assert 'get_client_file("ytd_account_setup.csv"' in text
    assert '_recover_ytd_account_setup' in text
    assert 'ytd_account_setup_recovered' in text


def test_ytd_ui_exposes_one_time_recovery_and_database_save_language():
    text = dashboard_js_text()
    assert 'recoverYtdAccountSetup' in text
    assert 'Recover previous setup' in text
    assert 'save to the local database' in text
    assert 'CSV remains an import/export adapter' in text
