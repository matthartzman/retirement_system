"""#330 bug fix (A3): a plan whose Optional Functions rows predate a
catalog module has no toggle row for it, so Plan Features shows no switch --
``backfill_optional_function_rows`` appends the missing rows (valued at the
module's current effective state) so the page can show and edit them."""

from src.module_catalog import CATALOG, GATE_MODULE_TOGGLE
from src.server_services.config_service import backfill_optional_function_rows


def test_missing_module_toggle_rows_are_backfilled():
    rows = [{"section": "Optional Functions", "label": "roth_conversion_plan", "value": "TRUE"}]
    out = backfill_optional_function_rows(rows, effective={"housing_location_search": True})
    labels = {r["label"] for r in out}
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by and not m.gated_by_any_flag and m.csv_row}
    assert toggles <= labels
    hls = next(r for r in out if r["label"] == "housing_location_search")
    assert hls["value"] == "TRUE"
    assert out[0] == rows[0]  # existing rows untouched, order kept


def test_backfilled_row_defaults_to_true_when_not_in_effective_map():
    out = backfill_optional_function_rows([], effective={})
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by and not m.gated_by_any_flag and m.csv_row}
    # effective.get(key, True) -- absent from the effective map defaults to on,
    # not off, so a module missing its row (e.g. an older plan folder) does not
    # silently switch itself off the moment this backfill runs.
    for r in out:
        if r["label"] in toggles:
            assert r["value"] == "TRUE"


def test_module_already_present_is_not_duplicated():
    rows = [{"section": "Optional Functions", "label": "housing_location_search", "value": "FALSE"}]
    out = backfill_optional_function_rows(rows, effective={"housing_location_search": True})
    matches = [r for r in out if r["label"] == "housing_location_search"]
    assert len(matches) == 1
    assert matches[0]["value"] == "FALSE"  # untouched, not overwritten by `effective`


def _store_rows_payload(store):
    """Minimal stand-in for app_core._csv_rows_payload: a real row_index (the row id) per
    plan row, in order -- enough to prove a backfilled row gets one it can actually be saved
    against, without pulling in the full server module."""
    return lambda: {"rows": [{"row_index": r["row_id"], "section": r["section"], "subsection": r["subsection"],
                               "label": r["label"], "value": r["value"]} for r in store.all_rows()],
                    "schema_count": 0}


def _optional_functions_service(tmp_path, *, load_active_config, edits=None):
    """A ConfigService over a real plan file whose Optional Functions section predates the
    catalog modules (it holds only ``roth_conversion_plan``). ``edits`` collects one entry per
    edit transaction opened. Returns ``(service, store)``."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from src.server_services.config_service import ConfigService, ConfigServiceContext
    from src.stores import PlanStore

    store = PlanStore.open(tmp_path / "unit.rpx", create=True)
    store.insert_row("Optional Functions", subsection="", label="roth_conversion_plan", value="TRUE",
                     units="boolean", notes="Roth Conversion")

    @contextmanager
    def read_plan():
        yield store

    @contextmanager
    def edit_plan():
        if edits is not None:
            edits.append(True)
        with store.transaction():
            yield SimpleNamespace(store=store)

    service = ConfigService(ConfigServiceContext(
        version="9",
        base_dir=tmp_path,
        edit_plan=edit_plan,
        read_plan=read_plan,
        csv_rows_payload=_store_rows_payload(store),
        read_schema_map=lambda: {},
        load_active_config=load_active_config,
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": "", "config_backend": "SQLITE"})(),
        normalize_date_for_csv=lambda value: value,
    ))
    return service, store


def _toggle_labels(store):
    return {r["label"] for r in store.rows("Optional Functions")}


def test_config_rows_payload_backfills_the_missing_toggle_into_the_plan_rows(tmp_path):
    """End-to-end: a plan that predates a catalog module has no row for it --
    config_rows_payload() must insert the missing row into the plan rows (one edit
    transaction) before the row payload is assembled, so the new row carries a real,
    persisted row_index rather than being invisible or a synthetic row nothing could save."""
    edits: list = []
    service, store = _optional_functions_service(
        tmp_path, load_active_config=lambda: ({}, {"backend": "SQLITE"}), edits=edits)

    payload, status = service.config_rows_payload()
    assert status == 200

    labels = {r["label"] for r in payload["rows"]}
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by and not m.gated_by_any_flag and m.csv_row}
    # Every switchable module now has a row -- the missing-row bug is fixed.
    assert toggles <= labels
    # It was actually written to the plan rows, not just synthesized for this one response.
    assert len(edits) == 1 and "housing_location_search" in _toggle_labels(store)
    # And it has a real row_index -- distinct per row, not a placeholder --
    # so the ordinary editValue(row_index) toggle path can act on it.
    row_indices = [r["row_index"] for r in payload["rows"]]
    assert len(row_indices) == len(set(row_indices))
    hls_row = next(r for r in payload["rows"] if r["label"] == "housing_location_search")
    assert isinstance(hls_row["row_index"], int)

    # Idempotent: calling again opens no further edit.
    service.config_rows_payload()
    assert len(edits) == 1


# Pinned explicitly (not `next(...)` over the catalog, and deliberately not
# `roth_conversion_plan` -- that key is already a seeded row in the fixture
# CSV above, so using it would never exercise the backfill path at all).
_BACKFILL_TOGGLE_KEY = "housing_location_search"


def test_backfilled_row_never_loads_active_config(tmp_path, monkeypatch):
    """Final review (Important #2/#3, A3), strengthened by a later review
    round: the backfill must never call ``load_active_config()`` /
    ``module_status()`` at all -- not "call it but ignore a disabled
    result." #330 Q7 deliberately never made the RETIREMENT_SYSTEM_FORCE_*
    tier a writable path, and this backfill writes straight to the plan's
    permanent CSV/SQLite store on a mere GET.

    A helper that raises on call cannot distinguish "never called" from
    "called, but the exception was swallowed by a broad ``except
    Exception``" -- the pre-fix code wrapped its ``load_active_config()``
    call in exactly such a ``try/except Exception: status = {}``, and
    ``AssertionError`` is an ``Exception`` subclass. So instead this test
    *records* every call and asserts the list stays empty.
    """
    from src.module_catalog import CATALOG, GATE_MODULE_TOGGLE

    key = _BACKFILL_TOGGLE_KEY
    m = CATALOG[key]
    assert m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by, (
        f"{key!r} must be a switchable module-toggle for this test to "
        "exercise the backfill path"
    )

    calls: list[None] = []

    def _record_and_return():
        calls.append(None)
        return ({}, {"backend": "SQLITE"})

    service, store = _optional_functions_service(tmp_path, load_active_config=_record_and_return)

    service._backfill_optional_function_rows()

    assert calls == [], (
        "load_active_config() must not be called at all when computing "
        "which rows are missing -- that is a pure catalog-vs-existing-"
        "labels comparison with no config load in it"
    )
    row = next(r for r in store.rows("Optional Functions") if r["label"] == key)
    assert row["value"] == "TRUE"


def test_backfilled_row_ignores_disabled_module_status(tmp_path, monkeypatch):
    """Companion to the "never loads config" test above: even if something
    upstream *did* wire up a module-status lookup that reports this toggle
    disabled (e.g. an env FORCE_DISABLE override folded into
    ``module_status()[key]["enabled"]``), the backfilled row must still be
    written "TRUE" -- the standard missing-row default -- not "FALSE".

    Reproduces the review's env-override scenario concretely: monkeypatches
    ``ConfigService._module_status`` (the method the pre-fix code called,
    via ``self._module_status(_data)``, to build its ``effective`` map) so
    that if it *were* consulted, it would report ``key`` as disabled.
    Against the pre-fix implementation (see ``git show a928fde --
    src/server_services/config_service.py``), which computed
    ``effective = {k: bool(status.get(k, {}).get("enabled", True)) ...}``
    from exactly this method and passed it into
    ``backfill_optional_function_rows``, this stub would have flipped the
    written value to "FALSE". Against the fixed code, which never calls
    ``_module_status`` from the backfill path, the stub is never consulted
    and the row is still written "TRUE".
    """
    from src.module_catalog import CATALOG, GATE_MODULE_TOGGLE
    from src.server_services.config_service import ConfigService

    key = _BACKFILL_TOGGLE_KEY
    m = CATALOG[key]
    assert m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by

    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", key)
    monkeypatch.setattr(
        ConfigService, "_module_status",
        staticmethod(lambda sectioned_data: {key: {"enabled": False}}),
    )

    service, store = _optional_functions_service(
        tmp_path, load_active_config=lambda: ({}, {"backend": "SQLITE"}))

    service._backfill_optional_function_rows()

    row = next(r for r in store.rows("Optional Functions") if r["label"] == key)
    assert row["value"] == "TRUE"
