"""Conversion step C6a: the legacy ``system_config.csv`` -> app.db settings and plan knobs.

WP8.1 deleted ``system_config.csv`` without an import: its runtime flags became built-in
defaults (``system_config.SYSTEM_DEFAULTS``) overlaid by ``app.db`` settings, and its engine
knobs (Rebalancing, Asset Class Assumptions, Asset Correlations, Annuity Calibration, Plan
Settings) became plan rows with code defaults (``engine_defaults``). This step carries an old
install's edited values across once:

* **runtime flags**: a row of ``SYSTEM_DEFAULTS`` whose CSV value differs from the default is
  written to ``app.db`` settings, unless app.db already stores that key (a value set in the new
  version wins). Secret rows (``units = secret``, the API keys) are never copied into settings
  (C6b moves keys); their count is reported.
* **engine knobs**: the old loader let the CSV win over the plan, the new one lets the plan
  row win. A knob the plan lacks is written to the plan when the CSV value differs from the
  code default. A knob the plan already holds is overwritten with the CSV value only when the
  plan rows were converted from the legacy CSV set by C3 (that plan computed under "CSV wins");
  a plan that already lived in a plan file keeps its rows (counted as ``knobs_kept``).
* every other row (the deleted path settings, the dropped dead rows) is ignored and counted.

Not repeated here (WP8.3 imports them once, lazily, on first use): ``data/prefs.json``, backup
and Monarch policy / status, workbook width overrides, the price cache and backup manifests.

``run(ctx_like)`` takes the open plan ``store``, the legacy CSV text (or None), the ``app.db``
path and ``dry_run``; markers: ``plan_meta['legacy_conversion.c6a']`` (knobs) and the app.db
setting ``legacy_conversion.c6a`` (flags). Values are never reported, only counts and names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...csv_exchange import parse_plan_csv
from ...engine_defaults import ENGINE_DEFAULT_ROWS
from ...system_config import SYSTEM_DEFAULTS, setting_key
from .c3_plan_rows import MARKER_KEY as C3_MARKER

STEP_ID = "C6a"
MARKER_KEY = "legacy_conversion.c6a"
LEGACY_FILE = "system_config.csv"

_FLAGS = {(s, ss, l): (v, u) for s, ss, l, v, u, _ in SYSTEM_DEFAULTS}
_KNOBS = {(s, ss, l): (v, u) for s, ss, l, v, u, _ in ENGINE_DEFAULT_ROWS}
_KNOB_SECTIONS = {s for s, _, _ in _KNOBS}


@dataclass
class C6aReport:
    step: str
    skipped: bool
    flags_written: list[str] = field(default_factory=list)
    flags_kept: int = 0
    secret_rows_skipped: int = 0
    knobs_written: list[str] = field(default_factory=list)
    knobs_kept: int = 0
    ignored_rows: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "skipped": self.skipped, "flags_written": list(self.flags_written),
                "flags_kept": self.flags_kept, "secret_rows_skipped": self.secret_rows_skipped,
                "knobs_written": list(self.knobs_written), "knobs_kept": self.knobs_kept,
                "ignored_rows": self.ignored_rows}


def classify(text: str) -> tuple[dict[tuple, str], dict[tuple, str], int, int]:
    """Pure: ``(runtime flags differing from default, engine knob rows, secret rows, ignored)``."""
    flags: dict[tuple, str] = {}
    knobs: dict[tuple, str] = {}
    secrets = ignored = 0
    for row in parse_plan_csv(text, LEGACY_FILE).rows:
        key = (row.section, row.subsection, row.label)
        value = row.value.strip()
        if key in _FLAGS:
            default, units = _FLAGS[key]
            if units == "secret":
                secrets += 1 if value else 0
            elif value != default:
                flags[key] = value
        elif row.section in _KNOB_SECTIONS:
            knobs[key] = value
        else:
            ignored += 1
    return flags, knobs, secrets, ignored


def run(store: Any, legacy_text: str | None, app_db: Path, *, dry_run: bool = False) -> C6aReport:
    from ...app_state import open_app_store  # noqa: PLC0415

    plan_done = store.get_meta(MARKER_KEY) is not None
    app_done = False
    if Path(app_db).is_file():
        with open_app_store(app_db, readonly=True) as app:
            app_done = app.get_setting(MARKER_KEY) is not None
    if legacy_text is None or (plan_done and app_done):
        return C6aReport(STEP_ID, skipped=True)
    flags, knobs, secrets, ignored = classify(legacy_text)
    rep = C6aReport(STEP_ID, skipped=False, secret_rows_skipped=secrets, ignored_rows=ignored)
    if not plan_done:
        csv_wins = store.get_meta(C3_MARKER) is not None
        with store.transaction():
            for (sec, sub, lbl), value in knobs.items():
                rows = store.find_rows(sec, sub, lbl)
                default = _KNOBS.get((sec, sub, lbl), (None, None))
                if rows:
                    if csv_wins and rows[-1]["value"] != value:
                        store.set_value(sec, sub, lbl, value)
                        rep.knobs_written.append(setting_key(sec, sub, lbl))
                    elif rows[-1]["value"] != value:
                        rep.knobs_kept += 1
                elif value != default[0]:
                    store.set_value(sec, sub, lbl, value, units=default[1] or "")
                    rep.knobs_written.append(setting_key(sec, sub, lbl))
            store.set_meta(MARKER_KEY, f"knobs={len(rep.knobs_written)}")
    if not app_done:
        stored: dict[str, Any] = {}
        if Path(app_db).is_file():
            with open_app_store(app_db, readonly=True) as app:
                stored = app.settings()
        todo = {k: v for k, v in flags.items() if setting_key(*k) not in stored}
        rep.flags_kept = len(flags) - len(todo)
        rep.flags_written = sorted(setting_key(*k) for k in todo)
        if not dry_run:
            with open_app_store(app_db) as app, app.transaction():
                for key, value in todo.items():
                    app.set_setting(setting_key(*key), value)
                app.set_setting(MARKER_KEY, f"flags={len(todo)}")
    return rep
