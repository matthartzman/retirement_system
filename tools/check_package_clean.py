"""Fail a release build when runtime artifacts or populated auth/state data are packaged."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'local_state' / 'retirement_system_v10.db'
FORBIDDEN_GLOBS = ('**/__pycache__', '**/*.pyc', '**/*.pyo')
ALLOW_NONEMPTY_TABLES = set()  # schema-only DB only
FORBIDDEN_PATHS = (
    '.claude',
    'data',
    'src/frontend',
    'output',
    'saved_plans',
    'local_state',
    'local_state/retirement_system_v10.db',
    'local_state/secrets.db',
    'output/retirement_dashboard_ui.html',
    'output/market_price_cache.json',
    'output/live_pricing_test_results.json',
)
ROOT_LAUNCHER_NAMES = {
    'START_UI.py', 'START_SERVER.py', 'START_UI.command', 'START_SERVER.command',
    'START_SERVER.sh', 'START_SERVER.bat', 'start_ui.bat', 'start_ui.sh',
    'start_wsgi_server.bat', 'start_wsgi_server.sh', 'RESET_TO_LOCAL_MODE.bat',
    'RESET_TO_LOCAL_MODE.sh', 'INSTALL_DESKTOP_ICON.py',
}


def main() -> int:
    errors: list[str] = []
    for pattern in FORBIDDEN_GLOBS:
        for path in ROOT.glob(pattern):
            errors.append(f'Forbidden runtime artifact: {path.relative_to(ROOT)}')

    for rel in FORBIDDEN_PATHS:
        path = ROOT / rel
        if path.exists():
            errors.append(f'Forbidden packaged path: {rel}')


    if not (ROOT / 'src' / 'server' / 'wsgi.py').exists():
        errors.append('Packaged release must include canonical WSGI entry point at src/server/wsgi.py.')

    if (ROOT / 'input').exists():
        errors.append('Packaged release must not include input/ Plan Data; load or select a Plan Data folder at runtime.')
    if (ROOT / 'output').exists():
        errors.append('Secure release package must not include output directory or generated reports.')
    if (ROOT / 'data').exists():
        errors.append('Secure release package must not include desktop/webview profile data.')
    if (ROOT / 'saved_plans').exists():
        errors.append('Secure release package must not include saved plan snapshots.')
    if (ROOT / 'local_state').exists():
        errors.append('Secure release package must not include local SQLite/runtime state.')
    if (ROOT / 'sample_plan_data').exists():
        errors.append('Deprecated sample_plan_data/ folder must not be packaged.')

    for path in ROOT.glob('RELEASE_NOTES*.md'):
        errors.append(f'Release note must be under documentation/release_notes/: {path.relative_to(ROOT)}')
    for path in ROOT.glob('*README*.md'):
        errors.append(f'README must be under documentation/readme/: {path.relative_to(ROOT)}')
    for path in ROOT.rglob('*README*.md'):
        if not path.is_relative_to(ROOT / 'documentation' / 'readme'):
            errors.append(f'README must be under documentation/readme/: {path.relative_to(ROOT)}')
    for name in ROOT_LAUNCHER_NAMES:
        if (ROOT / name).exists():
            errors.append(f'Launcher/desktop helper must be under tools/: {name}')

    code_roots = [ROOT / 'src', ROOT / 'frontend', ROOT / 'tools']
    forbidden_code_tokens = [
        '/api/v7', 'v7_routes', 'include_in_optimizer', 'count_towards_asset_class',
        'manual_selection_action', 'allocation_action', 'retirement_dashboard_ui.html',
    ]
    for base in code_roots:
        if not base.exists():
            continue
        for path in base.rglob('*'):
            if path.is_dir() or any(part in {'.pytest_cache', '__pycache__'} for part in path.parts):
                continue
            if path.name == 'check_package_clean.py' or path == Path(__file__).resolve():
                continue
            if path.suffix.lower() in {'.pyc', '.pyo', '.db', '.xlsx', '.pdf', '.png'}:
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except Exception:
                continue
            for token in forbidden_code_tokens:
                if token in text:
                    errors.append(f'Forbidden legacy/backward-compatibility token {token!r} in {path.relative_to(ROOT)}')


    deprecated_allocation_count_labels = {
        "_".join(parts) for parts in [
            ("count", "social", "security", "toward", "fixed", "income", "target"),
            ("count", "pension", "toward", "fixed", "income", "target"),
            ("count", "annuity", "toward", "fixed", "income", "target"),
            ("count", "note", "receivable", "toward", "fixed", "income", "target"),
            ("count", "home", "equity", "toward", "reit", "target"),
        ]
    }
    for base in [ROOT / "reference_data", ROOT / "frontend"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_dir() or path.suffix.lower() in {".db", ".xlsx", ".pdf", ".png"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for token in deprecated_allocation_count_labels:
                if token in text:
                    errors.append(f"Deprecated allocation input {token!r} remains in {path.relative_to(ROOT)}")

    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            for table in tables:
                n = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                if n and table not in ALLOW_NONEMPTY_TABLES:
                    errors.append(f'Packaged DB table {table} has {n} rows; expected schema-only DB')
            conn.close()
        except Exception as exc:
            errors.append(f'Could not inspect packaged SQLite DB: {exc}')

    if errors:
        print('PACKAGE CLEAN CHECK FAILED')
        for err in errors:
            print(f'- {err}')
        return 1
    print('PACKAGE CLEAN CHECK PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
