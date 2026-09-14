# Retirement Planner

Local-only retirement planning workspace for entering Plan Data, saving to the
SQLite working copy, building report outputs, and reviewing the advisor package.

## Running the app

Double-click the desktop shortcut (or `launchers/START_APP.bat`) to open the
planner. Everything you enter is saved automatically to a local database on
this computer — nothing is sent anywhere over the internet. Use the
in-app **Build** screen to generate the Excel/PDF report package once your
Plan Data is complete.

## Optional features

**Monarch auto-update** — if you export transactions from Monarch Money, this
app can automatically pull in new and changed transactions once a day. Turn
it on from **Settings → Data & Maintenance → Monarch auto-update**: check
"Enable daily auto-update," confirm the source folder, and it saves on its
own — no separate save button. Use **Import now** on the same card any time
you want to pull in the latest export without waiting for the daily run.

**Financial trends reporter** — a small companion dashboard that charts your
net worth and spending over time, alongside the main planner. Run it with
`python financial_trends_reporter/main.py` from this folder; it opens its own
browser tab showing a running history built from the same plan data. To have
it log a fresh snapshot automatically every weekday at 5pm instead of only
when you open it, run
`financial_trends_reporter/tools/launchers/register_trends_report_task.ps1`
once to register the scheduled task.

The sections below are for developers working on the source code, not for
running the packaged application.

The active source of truth is the local database under `local_state/`. CSV,
JSON, and YAML files are compatibility adapters for import/export and recovery.

Common commands:

- Start the app: `python main.py`
- Build outputs: `python tools/build_workbook.py`
- Run tests: `python -m pytest`

