# Retirement Planner v11

Local-only retirement planning workspace for entering Plan Data, saving to the
SQLite working copy, building report outputs, and reviewing the advisor package.

## Running the app

Double-click the desktop shortcut (or `launchers/START_APP.bat`) to open the
planner. Everything you enter is saved automatically to a local database on
this computer — nothing is sent anywhere over the internet. Use the
in-app **Build** screen to generate the Excel/PDF report package once your
Plan Data is complete.

The sections below are for developers working on the source code, not for
running the packaged application.

The active source of truth is the local database under `local_state/`. CSV,
JSON, and YAML files are compatibility adapters for import/export and recovery.

Common commands:

- Start the app: `python main.py`
- Build outputs: `python tools/build_workbook.py`
- Run tests: `python -m pytest`

