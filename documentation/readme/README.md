# Retirement Planner v10

Local-only retirement planning workspace for entering Plan Data, saving to the
SQLite working copy, building report outputs, and reviewing the advisor package.

The active source of truth is the local database under `local_state/`. CSV,
JSON, and YAML files are compatibility adapters for import/export and recovery.

Common commands:

- Start the app: `python main.py`
- Build outputs: `python tools/build_workbook.py`
- Run tests: `python -m pytest`

