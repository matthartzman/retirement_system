"""WP10.1: conversion runner skeleton (ordering, markers, dry run, originals untouched).

WP10.3: the low-level runner never sets the done marker (``convert_workspace`` does, after
verification); the plan and install phases are separate step lists."""
from __future__ import annotations

import pytest

from src.legacy_conversion import runner
from src.stores import PlanStore
from tests import plan_fixture as pf


def _ws(tmp_path):
    return pf.make_plan(tmp_path)


def test_runs_steps_in_order_and_leaves_sources_but_never_marks_done(tmp_path):
    ws = _ws(tmp_path)
    plan = tmp_path / "converted.rpx"
    rep = runner.run_conversion(tmp_path, plan, runner.DATASET_STEPS)
    assert rep.ok and rep.converted and rep.source_files > 0
    assert [s.step for s in rep.steps] == ["C3", "C3b", "C4a", "C4b", "C4c"]
    with PlanStore.open(plan, readonly=True) as store:
        assert store.get_meta("legacy_conversion.c3")
        # WP10.3: only convert_workspace sets the done marker, after verification.
        assert store.get_meta(runner.DONE_MARKER) is None


def test_rerun_is_a_noop_and_dry_run_touches_nothing(tmp_path):
    _ws(tmp_path)
    plan = tmp_path / "converted.rpx"
    dry = runner.run_conversion(tmp_path, plan, runner.DATASET_STEPS, dry_run=True)
    assert dry.ok and dry.dry_run and not plan.exists()
    runner.run_conversion(tmp_path, plan, runner.DATASET_STEPS)
    again = runner.run_conversion(tmp_path, plan, runner.DATASET_STEPS)
    assert again.ok and not again.converted
    assert all(s.status in {"skipped", "not_applicable"} for s in again.steps)


def test_failure_stops_run_without_message_and_no_done_marker(tmp_path):
    _ws(tmp_path)
    plan = tmp_path / "p.rpx"
    boom = runner.Step("X", lambda ctx: (_ for _ in ()).throw(ValueError("secret 123")))
    never = runner.Step("Y", lambda ctx: {})
    rep = runner.run_conversion(tmp_path, plan, (runner.DATASET_STEPS[0], boom, never))
    assert not rep.ok and [s.status for s in rep.steps][-1] == "failed"
    assert "secret" not in str(rep.as_dict()) and rep.steps[-1].error_type == "ValueError"
    assert len(rep.steps) == 2
    with PlanStore.open(plan, readonly=True) as store:
        assert store.get_meta(runner.DONE_MARKER) is None


def test_modified_source_is_detected(tmp_path):
    ws = _ws(tmp_path)
    target = ws.input_dir / "client_data.csv"
    bad = runner.Step("M", lambda ctx: target.write_text(target.read_text() + "\n") or {})
    with pytest.raises(runner.SourceModifiedError):
        runner.run_conversion(tmp_path, tmp_path / "p.rpx", (bad,))


def test_plan_and_install_phases_split_the_steps():
    plan_ids = [s.id for s in runner.PLAN_STEPS]
    install_ids = [s.id for s in runner.INSTALL_STEPS]
    assert plan_ids == ["SRC", "C3", "C3b", "C4a", "C4b", "C4c", "C6a", "T8"]
    assert install_ids == ["C6a.flags", "C6b", "C6c"]  # app.db, credential store, registry: after the swap
    assert [s.id for s in runner.CONVERSION_STEPS] == plan_ids + install_ids
