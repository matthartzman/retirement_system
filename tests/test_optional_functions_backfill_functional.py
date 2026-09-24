"""#330 bug fix (A3): a plan whose client_optional_functions.csv predates a
catalog module has no toggle row for it, so Plan Features shows no switch --
``backfill_optional_function_rows`` appends the missing rows (valued at the
module's current effective state) so the page can show and edit them."""

from src.module_catalog import CATALOG, GATE_MODULE_TOGGLE
from src.server_services.config_service import backfill_optional_function_rows


def test_missing_module_toggle_rows_are_backfilled():
    rows = [{"section": "Optional Functions", "label": "roth_conversion_plan", "value": "TRUE"}]
    out = backfill_optional_function_rows(rows, effective={"housing_location_search": True})
    labels = {r["label"] for r in out}
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by}
    assert toggles <= labels
    hls = next(r for r in out if r["label"] == "housing_location_search")
    assert hls["value"] == "TRUE"
    assert out[0] == rows[0]  # existing rows untouched, order kept


def test_backfilled_row_defaults_to_true_when_not_in_effective_map():
    out = backfill_optional_function_rows([], effective={})
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by}
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


def _csv_rows_from_file(path):
    """Minimal stand-in for app_core._csv_rows_payload: real row_index per
    row, in file order -- enough to prove a backfilled row gets one it can
    actually be saved against, without pulling in the full server module."""
    import csv as _csv
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for idx, cols in enumerate(_csv.reader(f)):
            cols = list(cols) + [""] * max(0, 6 - len(cols))
            rows.append({
                "row_index": idx, "section": cols[0].strip(), "subsection": cols[1].strip(),
                "label": cols[2].strip(), "value": cols[3].strip(),
            })
    return {"rows": rows, "schema_count": 0}


def test_config_rows_payload_backfills_the_missing_toggle_onto_disk(tmp_path):
    """End-to-end: a plan CSV that predates a catalog module has no row for
    it -- config_rows_payload() must write the missing row to disk (through
    write_plan_data_file, the existing save path) before the row payload is
    assembled, so the new row carries a real, persisted row_index rather
    than being invisible or a synthetic row nothing could save."""
    from src.server_services.config_service import ConfigService, ConfigServiceContext

    csv_path = tmp_path / "client_optional_functions.csv"
    csv_path.write_text(
        "section,subsection,label,value,units,notes\n"
        "Optional Functions,,roth_conversion_plan,TRUE,boolean,Roth Conversion\n",
        encoding="utf-8",
    )
    written = {}

    def write_plan_data(name, content):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        written[name] = content
        return p

    service = ConfigService(ConfigServiceContext(
        version="9",
        base_dir=tmp_path,
        csv_path=csv_path,
        plan_data_csv_files=["client_optional_functions.csv"],
        client_data_csv_file_set={"client_optional_functions.csv"},
        plan_data_path=lambda name, *a, **k: tmp_path / name,
        client_csv_rows=lambda: [],
        csv_rows_payload=lambda: _csv_rows_from_file(csv_path),
        read_schema_map=lambda: {},
        write_plan_data_file=write_plan_data,
        load_active_config=lambda: ({}, {"backend": "CSV"}),
        runtime_config=lambda: type("Cfg", (), {"sqlite_db": "", "config_backend": "CSV"})(),
        normalize_date_for_csv=lambda value: value,
        sync_config_backends=lambda: {"success": True},
    ))

    payload, status = service.config_rows_payload()
    assert status == 200

    labels = {r["label"] for r in payload["rows"]}
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by}
    # Every switchable module now has a row -- the missing-row bug is fixed.
    assert toggles <= labels
    # It was actually written to disk (through write_plan_data_file), not
    # just synthesized in memory for this one response.
    assert "client_optional_functions.csv" in written
    assert "housing_location_search" in csv_path.read_text(encoding="utf-8")
    # And it has a real row_index -- distinct per row, not a placeholder --
    # so the ordinary editValue(row_index) toggle path can act on it.
    row_indices = [r["row_index"] for r in payload["rows"]]
    assert len(row_indices) == len(set(row_indices))
    hls_row = next(r for r in payload["rows"] if r["label"] == "housing_location_search")
    assert isinstance(hls_row["row_index"], int)

    # Idempotent: calling again writes nothing further.
    written.clear()
    service.config_rows_payload()
    assert not written
