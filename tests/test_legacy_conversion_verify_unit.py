"""WP10.3: the conversion verifier's building blocks (``src/legacy_conversion/verify.py``).

The comparison primitives shared with ``tools/rehearse_conversion.py``, the old view's overlays
(dropped rows, override tables, engine knobs under C6a's rule), the reference plan file, the
legacy dataset reader and the cell-by-cell dataset check, and the engine's isolation.
"""
from __future__ import annotations

import os
import shutil

from src.legacy_conversion import runner, verify
from src.legacy_conversion.steps import c3b_plan_overrides
from src.stores import PlanStore
from tests import plan_fixture as pf

FROZEN = pf.fixture_dir("sample_frozen")


def test_diff_names_report_names_never_values():
    a = {"s": {"": {"x": 1.001, "y": "same", "z": [1, 2]}}, "only_a": {}}
    b = {"s": {"": {"x": 1.004, "y": "same", "z": [1, 3]}}}
    paths = verify.diff_names(verify.round_values(a), verify.round_values(b))
    assert paths == ["/only_a", "/s//z[1]"]  # 1.001 and 1.004 are the same to the cent
    assert dict(verify.name_summary(["/[3]/total_tax", "/[4]/total_tax", "/s//z[1]"])) == {"total_tax": 2, "z": 1}
    check = verify.compare("x", {"k": 5.0}, {"k": 6.0})
    assert check.status == verify.DIFF and check.names == ["/k"] and check.failed
    assert "6" not in str(check.as_dict()) and "5" not in str(check.as_dict())


def test_error_message_is_kept_out_of_every_serialized_form():
    check = verify.error_check("engine_output", ValueError("state SECRET_VALUE unknown"))
    assert check.error_type == "ValueError" and check.message  # for the rehearsal's --show-errors only
    assert "SECRET_VALUE" not in str(check.as_dict()) and "SECRET_VALUE" not in repr(check)


def test_old_view_drops_what_the_old_loader_dropped():
    data = {"Scenarios": {"Sell Home": {"home_value": "1", "sale_year": "2030"}},
            "section": {"subsection": {"label": "value"}}, "A": {"": {}}}
    assert verify.without_dropped(data) == {"Scenarios": {"Sell Home": {"sale_year": "2030"}}}


def test_knob_overlay_follows_c6a_rule():
    text = ("section,subsection,label,value,units,notes\n"
            "Rebalancing,Optimization,min_trade_amount,750,USD,\n"
            "Rebalancing,Optimization,max_tax_cost_bps,25,bps,\n"   # equals the code default
            "Rebalancing,Optimization,ltcg_rate,20.00%,pct,\n")
    plan = {"Rebalancing": {"Optimization": {"ltcg_rate": "15.00%"}}}
    kept = verify.with_knobs({k: {s: dict(v) for s, v in d.items()} for k, d in plan.items()}, text, csv_wins=False)
    assert kept["Rebalancing"]["Optimization"] == {"ltcg_rate": "15.00%", "min_trade_amount": "750"}
    won = verify.with_knobs({k: {s: dict(v) for s, v in d.items()} for k, d in plan.items()}, text, csv_wins=True)
    assert won["Rebalancing"]["Optimization"] == {"ltcg_rate": "20.00%", "min_trade_amount": "750"}


def test_override_overlay_lays_out_rows_as_c3b_writes_them(tmp_path):
    files = {"capital_market": "horizon_years,preset,asset_class,expected_return,volatility,notes\n"
                               "30,BASELINE,US Equity,7.5%,15%,mine\n,,,,,\n10,,Bonds,4%,,\n"}
    with PlanStore.open(tmp_path / "p.rpx") as store:
        c3b_plan_overrides.run(store, files)
        written = store.sectioned_data()
    assert verify.with_overrides({}, files) == written


def test_reference_file_holds_exactly_the_given_view(tmp_path):
    src = tmp_path / "plan.rpx"
    pf.make_plan(tmp_path)  # builds tmp_path/plan.rpx from the frozen fixture
    with PlanStore.open(src, readonly=True) as store:
        view = store.sectioned_data()
        holdings = store.dataset("holdings").count()
    first_sec = next(iter(view))
    first_sub = next(iter(view[first_sec]))
    first_lbl = next(iter(view[first_sec][first_sub]))
    view[first_sec][first_sub][first_lbl] = "changed"
    view.setdefault("New Section", {})["sub"] = {"added": "1"}
    dropped = next(iter(view["Household"][""]))
    del view["Household"][""][dropped]
    before = PlanStore.open(src, readonly=True)
    original = before.sectioned_data()
    before.close()
    ref = verify.write_rows_view(src, tmp_path / "ref.rpx", view)
    with PlanStore.open(ref, readonly=True) as store:
        assert store.sectioned_data() == view and store.dataset("holdings").count() == holdings
    with PlanStore.open(src, readonly=True) as store:
        assert store.sectioned_data() == original  # the source is only read


def test_legacy_dataset_rows_decode_like_the_old_readers(tmp_path):
    f = tmp_path / "client_holdings.csv"
    f.write_bytes(b"\xef\xbb\xbfaccount,symbol,shares\nA, VTI ,1\x00\n,,\nB,BND,2\n")
    header, rows = verify.legacy_dataset_rows(f)
    assert header == ["account", "symbol", "shares"]
    assert rows == [{"account": "A", "symbol": " VTI ", "shares": "1"}, {"account": "B", "symbol": "BND", "shares": "2"}]


def test_dataset_check_finds_a_changed_cell_by_column_name(tmp_path):
    ws = pf.make_plan(tmp_path / "ws")
    (ws.root / "plan.rpx").unlink()
    work = tmp_path / "work"
    staging = work / "plan.rpx"
    ctx, report = runner.run_plan_phase(ws.root, staging, runner.DATASET_STEPS, workdir=work)
    try:
        steps = {s.step: s.as_dict() for s in report.steps}
        check = verify.dataset_check(ctx.input_dir, staging, steps)
        assert check.status == verify.MATCH and check.compared > 0
        with PlanStore.open(staging) as store:
            rows = store.dataset("holdings").rows()
            rows[3]["shares"] = "999999"
            store.dataset("holdings").replace_all(rows[:-1])
        check = verify.dataset_check(ctx.input_dir, staging, steps)
        assert check.status == verify.DIFF and check.failed
        assert set(check.summary) >= {"shares", "holdings"}  # a cell and the row count, by name
        assert "999999" not in str(check.as_dict())
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_engine_isolation_restores_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_PLAN_DB", "/somewhere/plan.rpx")
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_ID", raising=False)
    live_app = tmp_path / "live_app.db"
    from src.app_state import open_app_store
    with open_app_store(live_app) as app:
        app.set_setting("x", 1)
    saved = {k: os.environ.get(k) for k in verify.Engine._KEYS}
    with verify.Engine(tmp_path / "engine", live_app):
        assert os.environ["RETIREMENT_SYSTEM_APP_DB"] == str(tmp_path / "engine" / "engine_app.db")
        assert os.environ["RETIREMENT_SYSTEM_PLAN_ID"] == verify.ENGINE_PLAN_ID
        with open_app_store(readonly=True) as app:
            assert app.get_setting("x") == 1  # a private copy of the install's settings
    assert {k: os.environ.get(k) for k in verify.Engine._KEYS} == saved


def test_nothing_converted_means_nothing_to_verify(tmp_path):
    inp = verify.VerifyInput(workspace=tmp_path, staging_file=tmp_path / "p.rpx", pre_tier_file=None, staged_dir=None,
                             initial={}, steps={"SRC": {"status": "skipped"}, "C3": {"status": "skipped"}}, workdir=tmp_path)
    checks = verify.verify_conversion(inp)
    assert {c.status for c in checks} == {verify.NOT_APPLICABLE} and not verify.failed(checks)
