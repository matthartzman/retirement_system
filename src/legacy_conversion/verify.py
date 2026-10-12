"""Verification of a conversion (WP10.3; design F section 8 item 6 / P8.3, tiers design section 6).

``convert_workspace`` converts into a STAGING copy of the plan and calls :func:`verify_conversion`
before anything becomes live; ``tools/rehearse_conversion.py`` runs the same checks on a copy of
a workspace and prints them. Every check reports counts and NAMES (section/subsection/label keys,
dataset columns, engine output keys, KPI names) only, never a value.

Checks (blocking: a difference or an error stops the conversion; the done marker is not set and
nothing becomes live until the user decides):

* ``plan_rows``: the plan rows the OLD loader gave the engine vs the converted plan (before the
  tier mapping). The old view is ``load_csv`` + ``migrate_sectioned_data`` over the staged plan
  CSV set when step C3 converted rows in this run (minus the rows the old loader dropped at every
  load), else the plan's own rows before the run; plus the override tables C3b converted and the
  engine knobs C6a carried from ``system_config.csv`` (C6a's documented rule). Compared with the
  engine knob defaults filled in on both sides (an absent knob reads as its default).
* ``engine_config`` / ``engine_output``: ``parse_client`` and the projection (``project``, Roth
  strategy scored, as the build reports it) of both views, each run against a plan file that
  holds exactly that view's rows (the reference file is the converted file patched to the old
  rows), live pricing off, with a private copy of app.db. Values compared to the cent. When no
  rows were converted from CSV in this run and both views are identical, the runs are not
  repeated (same inputs give the same results).
* ``datasets``: every flat dataset table and recovery copy converted in this run vs its staged
  legacy file: row counts and cell equality (cells exactly as typed), by column name. Legacy
  layouts are compared with C4b's documented mapping applied.
* ``tier_mapping``: the projection just before vs just after step T8 (feature-tiers safeguard):
  any difference blocks automatic migration; the differing engine keys are listed.

Advisory (reported, never blocking):

* ``old_build_kpis``: the deterministic KPIs of the last build the old version left
  (``kpi_snapshots`` of the legacy database, else ``output/plan_summary.json``) vs the converted
  plan's. The old build ran on another date with other prices, so a difference is a warning to
  show the user, not proof of a conversion fault.
* ``source_agreement``: files taken from ``input/`` whose legacy-database copy differs (the old
  app read a flat dataset's database copy first).
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

FLOAT_PLACES = 2
NAME_LIMIT = 40
# The projection the build reports scores the Roth strategy (``optimize_roth=True``); a test may
# turn this off for speed (the comparison logic is the same).
ROTH_OPTIMIZED = True
ENGINE_PLAN_ID = "conversion-check"
KPI_TOLERANCE = 0.01  # dollars

MATCH, DIFF, ERROR, SKIPPED, NOT_APPLICABLE = "match", "diff", "error", "skipped", "not_applicable"


# ----------------------------------------------------------------------------- comparison
def round_values(v: Any) -> Any:
    """``v`` with floats rounded to the cent (``FLOAT_PLACES``); engine helper objects compare by
    type name, not memory address."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        return round(v, FLOAT_PLACES)
    if isinstance(v, dict):
        return {str(k): round_values(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [round_values(x) for x in v]
    if isinstance(v, (str, int)):
        return v
    return f"<{type(v).__name__}>"


def diff_names(a: Any, b: Any, path: str = "", out: list[str] | None = None) -> list[str]:
    """Names (never values) of the keys at which two nested structures differ."""
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}")
            else:
                diff_names(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}[len]")
        for i, (x, y) in enumerate(zip(a, b)):
            diff_names(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(path)
    return out


def name_summary(paths: Iterable[str]) -> Counter:
    """Collapse diff paths to names: the last key that is not a list index
    (``/[3]/total_tax`` -> ``total_tax``)."""
    cols: Counter = Counter()
    for p in paths:
        parts = [s for s in p.split("/") if s and not s.startswith("[")]
        cols[(parts[-1].split("[")[0] if parts else "") or "(root)"] += 1
    return cols


def _leaves(v: Any) -> int:
    if isinstance(v, dict):
        return sum(_leaves(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return sum(_leaves(x) for x in v)
    return 1


@dataclass
class Check:
    name: str
    status: str
    blocking: bool = True
    compared: int = 0
    differing: int = 0
    names: list[str] = field(default_factory=list)  # differing keys (names only), capped
    summary: dict[str, int] = field(default_factory=dict)  # collapsed names -> count
    note: str = ""
    error_type: str = ""

    @property
    def failed(self) -> bool:
        return self.blocking and self.status in (DIFF, ERROR)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "status": self.status, "blocking": self.blocking,
                               "compared": self.compared, "differing": self.differing,
                               "names": list(self.names), "summary": dict(self.summary)}
        if self.note:
            out["note"] = self.note
        if self.error_type:
            out["error_type"] = self.error_type
        return out


def from_paths(name: str, paths: list[str], compared: int, *, blocking: bool = True, note: str = "") -> Check:
    return Check(name, DIFF if paths else MATCH, blocking, compared=compared, differing=len(paths),
                 names=paths[:NAME_LIMIT], summary=dict(name_summary(paths).most_common(NAME_LIMIT)), note=note)


def compare(name: str, a: Any, b: Any, *, blocking: bool = True, note: str = "") -> Check:
    """Check of two structures, values rounded to the cent."""
    ra, rb = round_values(a), round_values(b)
    return from_paths(name, diff_names(ra, rb), _leaves(ra), blocking=blocking, note=note)


def error_check(name: str, exc: BaseException, *, blocking: bool = True) -> Check:
    return Check(name, ERROR, blocking, error_type=type(exc).__name__, note="the engine raised; message withheld")


# ----------------------------------------------------------------------------- the engine
class Engine:
    """Runs ``parse_client`` / the projection against one plan file at a time, isolated from the
    install: the plan file is passed as ``RETIREMENT_SYSTEM_PLAN_DB`` (the engine reads its flat
    datasets and any plan rows it reads directly from there), the output id is fixed, live pricing
    is off and app.db is a private copy (the engine may create or write it). The environment is
    restored on exit. Not for use while the app serves requests (process-wide environment)."""

    _KEYS = ("RETIREMENT_SYSTEM_PLAN_DB", "RETIREMENT_SYSTEM_PLAN_ID", "RETIREMENT_SYSTEM_PLAN_REVISION",
             "RETIREMENT_SYSTEM_APP_DB", "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS")

    def __init__(self, workdir: Path, app_db: Path | None = None):
        self.workdir = Path(workdir)
        self.app_db = Path(app_db) if app_db else None
        self._saved: dict[str, str | None] = {}
        self._warm = False
        self._rows: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def __enter__(self) -> "Engine":
        from .. import plan_registry  # noqa: PLC0415
        from ..plan_db_replace import copy_sqlite_file  # noqa: PLC0415

        self.workdir.mkdir(parents=True, exist_ok=True)
        private = self.workdir / "engine_app.db"
        if self.app_db is not None and self.app_db.is_file():
            copy_sqlite_file(self.app_db, private)
        self._saved = {k: os.environ.get(k) for k in self._KEYS}
        os.environ["RETIREMENT_SYSTEM_APP_DB"] = str(private)
        os.environ["RETIREMENT_SYSTEM_PLAN_ID"] = ENGINE_PLAN_ID
        os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
        os.environ.pop("RETIREMENT_SYSTEM_PLAN_REVISION", None)
        plan_registry.invalidate()
        return self

    def __exit__(self, *exc: Any) -> None:
        from .. import plan_registry  # noqa: PLC0415

        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        plan_registry.invalidate()

    def _use(self, plan_file: Path, data: Mapping[str, Any]) -> None:
        from ..data_io import parse_client  # noqa: PLC0415

        os.environ["RETIREMENT_SYSTEM_PLAN_DB"] = str(plan_file)
        if not self._warm:
            # The first parse in a process can leave per-process state (price snapshots, lot ids)
            # behind; one warm-up parse keeps every compared run in the same state.
            self._warm = True
            try:
                parse_client(dict(data), "", skip_live_pricing=True)
            except Exception:  # noqa: BLE001 - the compared run reports it
                pass

    def config(self, plan_file: Path, data: Mapping[str, Any]) -> dict[str, Any]:
        from ..data_io import parse_client  # noqa: PLC0415

        self._use(plan_file, data)
        return parse_client(dict(data), "", skip_live_pricing=True)

    def rows(self, plan_file: Path, data: Mapping[str, Any]) -> list[dict[str, Any]]:
        from ..planning_engines import project  # noqa: PLC0415
        from ..report_compute import prepare_config_from_sectioned_data  # noqa: PLC0415

        key = (str(plan_file), json.dumps(data, sort_keys=True, default=str))
        if key not in self._rows:
            self._use(plan_file, data)
            cfg = prepare_config_from_sectioned_data(dict(data), "", optimize_roth=ROTH_OPTIMIZED,
                                                     skip_live_pricing=True)
            self._rows[key] = [dict(r) for r in project(cfg)]
        return self._rows[key]


def _plan_rows_of(plan_file: Path) -> dict[str, Any]:
    from ..active_plan import PlanStore  # noqa: PLC0415

    with PlanStore.open(plan_file, create=False, readonly=True) as store:
        return store.sectioned_data()


def write_rows_view(src: Path, dest: Path, rows: Mapping[str, Mapping[str, Mapping[str, str]]]) -> Path:
    """A copy of plan file ``src`` whose engine view of the rows is ``rows`` (rows that differ are
    set, missing keys added, extra keys removed); datasets and meta as in ``src``."""
    from ..active_plan import PlanStore  # noqa: PLC0415
    from ..plan_db_replace import copy_sqlite_file  # noqa: PLC0415

    copy_sqlite_file(src, dest)
    with PlanStore.open(dest, create=False) as store, store.transaction():
        have = store.sectioned_data()
        for row in store.all_rows():
            sec, sub, lbl = row["section"].strip(), row["subsection"].strip(), row["label"].strip()
            if sec in have and lbl and lbl not in (rows.get(sec, {}).get(sub, {})):
                store.delete_row(row["row_id"])
        for sec, subs in rows.items():
            for sub, labels in subs.items():
                for lbl, value in labels.items():
                    if have.get(sec, {}).get(sub, {}).get(lbl) != value:
                        store.set_value(sec, sub, lbl, str(value))
    return dest


# ----------------------------------------------------------------------------- reference view
def without_dropped(data: Mapping[str, Any]) -> dict[str, Any]:
    """``data`` without the rows the old loader dropped at every load (a repeated ``label``
    header row, the retired ``Scenarios / Sell Home`` labels) and without empty containers."""
    from ..plan_label_rules import dropped_at_load  # noqa: PLC0415

    out: dict[str, Any] = {}
    for sec, subs in data.items():
        for sub, labels in (subs or {}).items():
            for lbl, value in (labels or {}).items():
                if not dropped_at_load(sec, sub, lbl):
                    out.setdefault(sec, {}).setdefault(sub, {})[lbl] = value
    return out


def old_loader_rows(input_dir: Path) -> dict[str, Any]:
    """The old engine's view of a plan CSV set: ``load_csv`` + ``migrate_sectioned_data`` (the
    path ``config_backend`` took), minus the rows it dropped at load."""
    from ..csv_exchange import ANCHOR_FILE  # noqa: PLC0415
    from ..data_io import load_csv  # noqa: PLC0415
    from ..plan_data_migration import migrate_sectioned_data  # noqa: PLC0415

    data, _ = migrate_sectioned_data(load_csv(Path(input_dir) / ANCHOR_FILE))
    return without_dropped(data)


def with_overrides(data: dict[str, Any], files: Mapping[str, str]) -> dict[str, Any]:
    """``data`` with the custom reference files (``{kind: csv text}``) laid out as the override
    rows C3b writes (``plan_overrides.replace_rows``: a ``row_N`` subsection per row, one row per
    filled cell)."""
    from ..csv_exchange import parse_csv_dicts  # noqa: PLC0415
    from ..plan_overrides import COLUMNS, SECTIONS  # noqa: PLC0415
    from .steps.c3b_plan_overrides import convert  # noqa: PLC0415

    for kind, text in files.items():
        rows = convert(kind, parse_csv_dicts(text)) if text else []
        if not rows:
            continue
        data[SECTIONS[kind]] = {
            f"row_{i}": {c: str(r[c]).strip() for c in COLUMNS[kind] if str(r.get(c, "")).strip()}
            for i, r in enumerate(rows, 1)}
    return data


def with_knobs(data: dict[str, Any], system_config_text: str, *, csv_wins: bool) -> dict[str, Any]:
    """``data`` with the engine knobs of a legacy ``system_config.csv`` under C6a's rule: a knob
    the plan lacks is taken when it differs from the code default; a knob the plan holds is
    replaced only when the plan rows came from the CSV set (``csv_wins``: the old loader let the
    CSV win)."""
    from ..engine_defaults import ENGINE_DEFAULT_ROWS  # noqa: PLC0415
    from .steps.c6a_settings import classify  # noqa: PLC0415

    defaults = {r[:3]: r[3] for r in ENGINE_DEFAULT_ROWS}
    _flags, knobs, _secrets, _ignored = classify(system_config_text)
    for (sec, sub, lbl), value in knobs.items():
        held = data.get(sec, {}).get(sub, {})
        if lbl in held:
            if csv_wins:
                held[lbl] = value
        elif value != defaults.get((sec, sub, lbl)):
            data.setdefault(sec, {}).setdefault(sub, {})[lbl] = value
    return data


def normalized(data: Mapping[str, Any]) -> dict[str, Any]:
    """The comparable form of an engine view: dropped-at-load rows removed and the engine knob
    defaults filled in (an absent knob reads as its default)."""
    from ..engine_defaults import with_engine_defaults  # noqa: PLC0415

    return with_engine_defaults(without_dropped(data))


# ----------------------------------------------------------------------------- datasets
def legacy_dataset_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """``(header, rows)`` of a legacy flat dataset file as its old readers saw it: UTF-8 (BOM
    ignored, undecodable bytes replaced, NUL bytes dropped), cells as typed, blank rows skipped."""
    text = Path(path).read_bytes().decode("utf-8-sig", errors="replace").replace("\x00", "").lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    header = [str(c) for c in (reader.fieldnames or []) if c is not None and str(c)]
    rows = []
    for raw in reader:
        row = {str(k): (v or "") for k, v in raw.items() if k is not None and str(k)}
        if any(v.strip() for v in row.values()):
            rows.append(row)
    return header, rows


def _cell_paths(label: str, expected: list[dict[str, str]], actual: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    if len(expected) != len(actual):
        out.append(f"{label}[rows]")
    for e, a in zip(expected, actual):
        for col in sorted(set(e) | set(a)):
            if (e.get(col) or "") != (a.get(col) or ""):
                out.append(f"{label}/{col}")
    return out


def dataset_check(staged_dir: Path | None, plan_file: Path, steps: Mapping[str, Any]) -> Check:
    """Every flat dataset and recovery copy a step converted in this run vs its staged file."""
    from ..active_plan import PlanStore  # noqa: PLC0415
    from ..csv_exchange import FLAT_DATASET_FILES  # noqa: PLC0415
    from .steps import c4b_spending  # noqa: PLC0415

    written: dict[str, int] = {}
    for sid in ("C4a", "C4c"):
        detail = steps.get(sid) or {}
        if detail.get("status") == "converted":
            written.update((detail.get("detail") or {}).get("rows_written") or {})
    c4b = steps.get("C4b") or {}
    c4b_detail = (c4b.get("detail") or {}) if c4b.get("status") == "converted" else {}
    spending_names = {short: next(n for n, f in FLAT_DATASET_FILES.items() if f == file)
                      for short, file in c4b_spending.FILES.items()}
    for short in (c4b_detail.get("rows_written") or {}):
        if short in spending_names:
            written[spending_names[short]] = 1
    if c4b_detail.get("aliases_ignored"):
        written[spending_names["aliases"]] = 1
    recovery = [k for k in (c4b_detail.get("rows_written") or {}) if k in c4b_spending.RECOVERY_FILES]
    if not written and not recovery:
        return Check("datasets", NOT_APPLICABLE, note="no dataset converted in this run")
    if staged_dir is None:
        return Check("datasets", ERROR, error_type="NoStagedSources", note="staged legacy files missing")
    paths: list[str] = []
    compared = 0
    with PlanStore.open(plan_file, create=False, readonly=True) as store:
        for name in written:
            file = Path(staged_dir) / FLAT_DATASET_FILES[name]
            header, expected = legacy_dataset_rows(file) if file.is_file() else ([], [])
            if name == "spending_taxonomy" and c4b_detail.get("legacy_taxonomy_layout"):
                expected = [c4b_spending._legacy_taxonomy_row(r) for r in expected]  # noqa: SLF001 - C4b's mapping
            elif name == "spending_budget" and c4b_detail.get("legacy_budget_layout"):
                expected = c4b_spending._legacy_budget_rows(expected)  # noqa: SLF001 - C4b's mapping
            elif name == "spending_aliases" and c4b_detail.get("aliases_ignored"):
                expected = []  # the old reader ignored such a file
            actual = store.dataset(name).rows()
            compared += 1 + sum(len(r) for r in expected)
            paths += _cell_paths(name, expected, actual)
        for key in recovery:
            file = Path(staged_dir) / c4b_spending.RECOVERY_FILES[key]
            expected = legacy_dataset_rows(file)[1] if file.is_file() else []
            if key == "recovery_seed":
                actual = store.spending.recovery_seed()
            else:
                head = store.latest_revision("pre-recovery")
                actual = store.revision_dataset_rows(head["id"], "spending_budget") if head else []
            compared += 1 + sum(len(r) for r in expected)
            paths += _cell_paths(key, expected, actual)
    return from_paths("datasets", paths, compared,
                      note=f"{len(written)} table(s), {len(recovery)} recovery cop(ies) converted in this run")


# ----------------------------------------------------------------------------- old build KPIs
KPI_FROM_SUMMARY = {"terminal_nw": "terminal_nw_deterministic", "terminal_pretax_nw": "terminal_pretax_nw",
                    "terminal_roth_nw": "terminal_roth_nw", "lifetime_tax": "lifetime_tax",
                    "total_roth_conversions": "total_roth_conversions"}
KPI_NAMES = tuple(KPI_FROM_SUMMARY.values())


def kpis_from_rows(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    """The build's deterministic KPIs from projection rows (``workbook_builder``'s summary)."""
    if not rows:
        return {}
    last = rows[-1]
    return {"terminal_nw_deterministic": float(last.get("total_nw", 0.0) or 0.0),
            "terminal_pretax_nw": float(last.get("pretax_nw", 0.0) or 0.0),
            "terminal_roth_nw": float(last.get("roth_nw", 0.0) or 0.0),
            "lifetime_tax": sum(float(r.get("total_tax", 0.0) or 0.0) for r in rows),
            "total_roth_conversions": sum(float(r.get("roth_conv", 0.0) or 0.0) for r in rows)}


def _numeric(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN reads as missing


def old_build_kpis(workspace: Path, *, mode: str = "normal", legacy_db: Path | None = None) -> tuple[str, dict[str, float]] | None:
    """``(source, {kpi: value})`` of the last build the old version left: the newest
    ``kpi_snapshots`` row of the legacy database, else the newest ``output/plan_summary.json``
    (not for a mid-demo install, whose last build was the demo's). None when there is none."""
    from . import sources  # noqa: PLC0415

    ws = Path(workspace)
    db = legacy_db
    if db is None:
        live = sources.legacy_db_path(ws)
        db = live.with_name(live.name + sources.BEFORE_DEMO) if mode == "mid_demo" else live
    snap = sources.read_latest_kpis(db)
    if snap:
        vals = {k: v for k in ("terminal_nw_deterministic", "lifetime_tax", "total_roth_conversions")
                if (v := _numeric(snap.get(k))) is not None}
        if vals:
            return "kpi_snapshots", vals
    if mode == "mid_demo":
        return None
    out_dir = ws / "output"
    candidates = [out_dir / "plan_summary.json", *out_dir.glob("*/plan_summary.json"),
                  *out_dir.glob("plans/*/plan_summary.json")]
    found = sorted((p for p in candidates if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in found:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            vals = {name: v for key, name in KPI_FROM_SUMMARY.items() if (v := _numeric(data.get(key))) is not None}
            if vals:
                return "plan_summary.json", vals
    return None


def kpi_check(old: tuple[str, dict[str, float]] | None, new: Mapping[str, float]) -> Check:
    if not old:
        return Check("old_build_kpis", NOT_APPLICABLE, blocking=False, note="no results of an old build found")
    source, values = old
    names = [k for k, v in values.items() if k in new and abs(float(new[k]) - v) > max(KPI_TOLERANCE, abs(v) * 1e-9)]
    return from_paths("old_build_kpis", names, len(values), blocking=False,
                      note=f"vs {source}; the old build ran on another date with other prices, so a difference is a warning")


# ----------------------------------------------------------------------------- the run
@dataclass
class VerifyInput:
    """What :func:`verify_conversion` reads (paths into the run's scratch folder)."""

    workspace: Path
    staging_file: Path            # the converted plan (after every plan step)
    pre_tier_file: Path | None    # the staging plan just before T8 (None: T8 did not run)
    staged_dir: Path | None       # the staged legacy files (SRC)
    initial: Mapping[str, Any]    # runner.capture_initial of the staging plan before any step
    steps: Mapping[str, Mapping[str, Any]]  # step id -> StepResult.as_dict()
    workdir: Path
    app_db: Path | None = None
    mode: str = "normal"
    legacy_db: Path | None = None
    disagreeing_files: list[str] = field(default_factory=list)
    skip_engine: bool = False     # rehearsal --skip-engine only; never set by the converter


def _status(steps: Mapping[str, Mapping[str, Any]], sid: str) -> str:
    return str((steps.get(sid) or {}).get("status") or "")


def verify_conversion(inp: VerifyInput) -> list[Check]:
    """Run every check (see the module docstring); returns them in report order."""
    from .steps import c3_plan_rows, c3b_plan_overrides, c6a_settings, t8_tier_mapping  # noqa: PLC0415

    steps = inp.steps
    if not any(_status(steps, s) == "converted" for s in steps):
        note = "nothing converted in this run"
        return [Check(n, NOT_APPLICABLE, note=note) for n in ("plan_rows", "engine_config", "engine_output", "datasets", "tier_mapping")] + \
               [Check("old_build_kpis", NOT_APPLICABLE, blocking=False, note=note)]
    checks: list[Check] = []
    markers = inp.initial.get("markers") or {}
    converted_file = inp.pre_tier_file or inp.staging_file
    converted = _plan_rows_of(converted_file)

    # ---- the old view
    c3_now = _status(steps, "C3") == "converted"
    reference = old_loader_rows(inp.staged_dir) if c3_now and inp.staged_dir else \
        json.loads(json.dumps(inp.initial.get("rows") or {}))
    c3b_written = ((steps.get("C3b") or {}).get("detail") or {}).get("rows_written") or {}
    if _status(steps, "C3b") == "converted" and c3b_written and inp.staged_dir:
        files = {kind: (Path(inp.staged_dir) / name).read_text(encoding="utf-8-sig")
                 for kind, name in c3b_plan_overrides.LEGACY_FILES.items()
                 if kind in c3b_written and (Path(inp.staged_dir) / name).is_file()}
        reference = with_overrides(reference, files)
    sys_cfg = Path(inp.workspace) / c6a_settings.LEGACY_FILE
    if c6a_settings.MARKER_KEY not in markers and _status(steps, "C6a") == "converted" and sys_cfg.is_file():
        reference = with_knobs(reference, sys_cfg.read_text(encoding="utf-8-sig"),
                               csv_wins=c3_now or c3_plan_rows.MARKER_KEY in markers)
    rows_note = "old loader (load_csv + migrate) over the staged CSV set" if c3_now else "the plan's rows before the run"
    checks.append(compare("plan_rows", normalized(reference), normalized(converted), note=rows_note))

    t8 = steps.get("T8") or {}
    mapping = ((t8.get("detail") or {}).get("mapping")) if t8.get("status") == "converted" else None
    if inp.skip_engine:
        skipped = "engine runs skipped (rehearsal --skip-engine)"
        checks += [Check(n, SKIPPED, note=skipped) for n in ("engine_config", "engine_output")]
        checks.append(dataset_check(inp.staged_dir, inp.staging_file, steps))
        checks.append(Check("tier_mapping", SKIPPED if mapping else NOT_APPLICABLE, note=skipped))
        checks.append(Check("old_build_kpis", SKIPPED, blocking=False, note=skipped))
    else:
        with Engine(Path(inp.workdir) / "engine", inp.app_db) as engine:
            checks += _engine_fidelity(engine, inp, reference, converted, converted_file)
            checks.append(dataset_check(inp.staged_dir, inp.staging_file, steps))
            checks.append(_tier_check(engine, inp, mapping, t8_tier_mapping.MARKER_KEY in markers))
            checks.append(_kpi(engine, inp))
    checks.append(from_paths("source_agreement", list(inp.disagreeing_files), len(inp.disagreeing_files),
                             blocking=False, note="files taken from input/ whose legacy-database copy differs"))
    return checks


def _engine_fidelity(engine: Engine, inp: VerifyInput, reference: dict[str, Any], converted: dict[str, Any],
                     converted_file: Path) -> list[Check]:
    """``parse_client`` and the projection of the old view vs the converted plan. When the two
    views are identical one run serves both (same inputs, same results)."""
    same = reference == converted
    ref_file = converted_file if same else write_rows_view(converted_file, Path(inp.workdir) / "reference.rpx", reference)
    note = "old view identical to the converted plan: one engine run serves both" if same else ""
    out: list[Check] = []
    try:
        cfg_new = engine.config(converted_file, converted)
        cfg_ref = cfg_new if same else engine.config(ref_file, reference)
        out.append(compare("engine_config", cfg_ref, cfg_new, note=note))
    except Exception as exc:  # noqa: BLE001 - type only
        out.append(error_check("engine_config", exc))
    try:
        rows_new = engine.rows(converted_file, converted)
        rows_ref = rows_new if same else engine.rows(ref_file, reference)
        out.append(compare("engine_output", rows_ref, rows_new, note=note))
    except Exception as exc:  # noqa: BLE001 - type only
        out.append(error_check("engine_output", exc))
    return out


def _tier_check(engine: Engine, inp: VerifyInput, mapping: Mapping[str, Any] | None, done_before: bool) -> Check:
    if done_before or not mapping or inp.pre_tier_file is None:
        return Check("tier_mapping", NOT_APPLICABLE, note="no tier mapping applied in this run")
    switched = sorted([*mapping.get("turn_on", []), *mapping.get("turn_off", [])])
    note = f"tier {mapping.get('tier')}; switched: {', '.join(switched) or 'none'}"
    try:
        before = engine.rows(inp.pre_tier_file, _plan_rows_of(inp.pre_tier_file))
        after = engine.rows(inp.staging_file, _plan_rows_of(inp.staging_file))
    except Exception as exc:  # noqa: BLE001 - type only
        return error_check("tier_mapping", exc)
    return compare("tier_mapping", before, after, note=note)


def _kpi(engine: Engine, inp: VerifyInput) -> Check:
    try:
        old = old_build_kpis(inp.workspace, mode=inp.mode, legacy_db=inp.legacy_db)
    except Exception as exc:  # noqa: BLE001 - unreadable old results: report, never block
        return error_check("old_build_kpis", exc, blocking=False)
    if not old:
        return kpi_check(None, {})
    try:
        new = kpis_from_rows(engine.rows(inp.staging_file, _plan_rows_of(inp.staging_file)))
    except Exception as exc:  # noqa: BLE001 - type only
        return error_check("old_build_kpis", exc, blocking=False)
    return kpi_check(old, new)


def failed(checks: Iterable[Check]) -> list[Check]:
    return [c for c in checks if c.failed]


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
