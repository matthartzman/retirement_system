"""Plan Data save validation: format on save, 'required' at build (QA-002 / QA-003).

System review 2026-11-10, W2-01 and W2-02:
* a grid save validates format and range only, so Start New Plan can be filled in field by
  field; a build with a required value missing is still refused (W1-04 preflight);
* 'dollars' and 'decimal' are money types and use the one strict number grammar;
* every type in reference_src/schema.csv is handled by validate_value;
* the forms writer rejects the same bad money text the grid does.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

import src.server.app_core as app_core
from src.schema_registry import MONEY_TYPES, load_schema, validate_value
from src.server import app
from tests.plan_fixture import make_plan

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-User-Role": "admin"}
MORTGAGE = ("Cashflow", "Mortgage", "balance_as_of_plan_start")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


def _row_id(client, key):
    rows = client.get("/api/config/rows", headers=HEADERS).get_json()["rows"]
    return next(r["row_index"] for r in rows if (r["section"], r["subsection"], r["label"]) == key)


def test_blank_plan_can_be_saved_one_field_at_a_time_but_not_built(ws):
    app_core._blank_plan_rows()
    client = app.test_client()
    rid = _row_id(client, ("Household", "", "member_1_dob"))
    resp = client.post("/api/config/rows", headers=HEADERS,
                       json={"updates": [{"row_index": rid, "value": "1/1/1960"}]})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["updated"] == 1
    # Required values are still missing, so the build is refused.
    build = client.post("/api/build/start", headers=HEADERS)
    assert build.status_code == 409
    assert build.get_json()["blockers"]


def test_format_errors_are_still_rejected_with_the_field_errors_shape(ws):
    client = app.test_client()
    rid = _row_id(client, MORTGAGE)
    resp = client.post("/api/config/rows", headers=HEADERS,
                       json={"updates": [{"row_index": rid, "value": "about 300k"}]})
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["field_errors"] and body["field_errors"][0]["label"] == MORTGAGE[2]
    assert {"section", "subsection", "label", "message", "got", "raw"} <= set(body["field_errors"][0])


def test_required_is_only_checked_when_asked(ws):
    required = {"type": "dollars", "required": "TRUE"}
    assert validate_value("", required) == ["required value missing"]
    assert validate_value("", required, check_required=False) == []


@pytest.mark.parametrize("typ", sorted(MONEY_TYPES))
def test_every_money_type_uses_the_strict_number_grammar(typ):
    spec = {"type": typ}
    assert validate_value("abc", spec)
    assert validate_value("1_000", spec), "an underscore grouping is not part of the grammar"
    assert validate_value("nan", spec)
    assert not validate_value("$1,234.50", spec)
    assert not validate_value("(5,000)", spec)


def test_every_schema_type_is_handled():
    types = {(r.get("type") or "").lower() for r in csv.DictReader(
        (ROOT / "reference_src" / "schema.csv").open(encoding="utf-8-sig", newline=""))}
    known_money = set(MONEY_TYPES)
    known_other = {"percent", "pct", "integer", "year", "date", "boolean", "yes/no", "choice", "text", "secret"}
    assert types <= known_money | known_other, f"unhandled schema types: {types - known_money - known_other}"
    for typ in types & known_money:
        assert validate_value("abc", {"type": typ}), typ
    assert load_schema()


def test_forms_writer_rejects_bad_money_text(ws):
    client = app.test_client()
    patch = client.patch("/api/plan/forms/Cashflow/Mortgage", headers=HEADERS,
                         json={"values": {MORTGAGE[2]: "about 300k"}})
    assert patch.status_code == 422
    assert patch.get_json()["field_errors"][0]["label"] == MORTGAGE[2]
    post = client.post("/api/plan/forms", headers=HEADERS,
                       json={"sections": {"Cashflow": {"Mortgage": {MORTGAGE[2]: "about 300k"}}}})
    assert post.status_code == 422
    ok = client.patch("/api/plan/forms/Cashflow/Mortgage", headers=HEADERS,
                      json={"values": {MORTGAGE[2]: "$250,000"}})
    assert ok.status_code == 200
