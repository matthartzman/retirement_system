from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_backend import (
    DEFAULT_DB,
    import_csv_to_sqlite,
    init_sqlite,
    load_clients_csv,
    load_csv,
    export_client_json_yaml,
    sync_clients_csv_to_sqlite,
    set_client_file,
)
from src.runtime_config import load_runtime_config

PLAN_FILES = [
    'client_data.csv',
    'client_household.csv',
    'client_income.csv',
    'client_spending.csv',
    'client_assets.csv',
    'client_policy.csv',
    'client_insurance_estate.csv',
    'client_optional_functions.csv',
    'client_holdings.csv',
    'target_allocation.csv',
    'client_data.json',
    'client_data.yaml',
    'client_household.json',
    'client_income.json',
    'client_spending.json',
    'client_assets.json',
    'client_policy.json',
    'client_insurance_estate.json',
    'client_optional_functions.json',
    'client_household.yaml',
    'client_income.yaml',
    'client_spending.yaml',
    'client_assets.yaml',
    'client_policy.yaml',
    'client_insurance_estate.yaml',
    'client_optional_functions.yaml',
]


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main() -> int:
    cfg = load_runtime_config()
    db = init_sqlite(_resolve(cfg.sqlite_db or DEFAULT_DB))
    print('Writing v10 JSON/YAML config exports and local SQLite backend...')

    active_csv = _resolve(cfg.config_file or 'input/client_data.csv')
    if active_csv.exists():
        exports = export_client_json_yaml(active_csv, active_csv.parent)
        for name, path in sorted(exports.items()):
            print(path)
        print(import_csv_to_sqlite(active_csv, db, workspace_id=cfg.workspace_id or 'local'))
    else:
        print(f'Active config file not found, skipped import: {active_csv}')

    clients_csv = _resolve(cfg.clients_file) if cfg.clients_file else None
    clients = []
    if clients_csv and clients_csv.exists():
        print(f"Synced clients: {sync_clients_csv_to_sqlite(clients_csv, db)}")
        clients = load_clients_csv(clients_csv)
    else:
        print('No client registry configured; initialized local single-plan backend only.')

    for client in clients:
        workspace = client.get('workspace_id') or client.get('client_id') or 'local'
        client_id = client.get('client_id') or workspace
        cfg_ref = _resolve(client.get('config_ref') or 'input/client_data.csv')
        if cfg_ref.exists():
            workspace_exports = export_client_json_yaml(cfg_ref, cfg_ref.parent)
            for _, path in sorted(workspace_exports.items()):
                print(path)
            print(import_csv_to_sqlite(cfg_ref, db, workspace_id=workspace))
        input_dir = cfg_ref.parent
        for name in PLAN_FILES:
            p = input_dir / name
            if p.exists():
                set_client_file(name, p.read_text(encoding='utf-8'), workspace_id=workspace, client_id=client_id, updated_by='init_backend', db_path=db)
                print(f'Stored SQLite client file for {workspace}: {name}')
    print(f'Backend ready: {db}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
