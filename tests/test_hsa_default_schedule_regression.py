"""Default HSA schedule for 'optimize' mode (2026-08-20).

The bug this closes: with no client_hsa_schedule.csv, withdraw_hsa_window's
'optimize' branch fell back to a PER-YEAR-recalculated level draw
(total remaining balance / years remaining to plan_end, re-evaluated fresh
every year). That formula is mathematically guaranteed to draw 100% of
whatever is left in the account's FINAL year -- years_remaining hits exactly
1 there, collapsing the formula to "draw everything" regardless of how the
balance drifted from the original plan by then. A real user hit this: eight
years of a smoothly-growing few-thousand-dollar draw, then an $82,904 dump
in the plan's last year, read (wrongly) as "the optimizer decided to."

The fix is generate_default_schedule (src/hsa_schedule.py): a STATIC,
level-draw schedule computed ONCE, up front, against the shorter
mortality-percentile deadline (resolve_consume_by_year) rather than the
household's full life horizon. Because every year's share is fixed the
moment the function returns, no later year's draw can depend on how much
balance happens to be left by the time that year arrives -- the mechanism
that produced the cliff cannot exist in a flat schedule by construction.

_ensure_hsa_default_schedule (src/reporting/workbook_builder.py) writes this
once, the first time a build runs in 'optimize' mode with no schedule file --
never overwriting an existing one, so a household's own entries (or a future
real optimizer run) always win the moment they exist.
"""
from __future__ import annotations

import re

from src.hsa_schedule import generate_default_schedule
from src.planning_engines import withdraw_hsa_window


def _c(plan_start=2026, plan_end=2056, balances=None, hsa_ids=("hsa1",), consume_by=None):
    c = {
        "plan_start": plan_start,
        "plan_end": plan_end,
        "hsa_ids": list(hsa_ids),
        "balances": balances or {},
        "members": [],
    }
    if consume_by is not None:
        c["hsa_consume_by"] = consume_by
    return c


# --- generate_default_schedule: pure function -------------------------------


def test_level_draw_divides_the_balance_evenly_across_the_horizon():
    # Explicit year deadline, so the math is exact and independent of the
    # mortality table: 2026..2030 inclusive is 5 years.
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 100_000.0}, consume_by="2030")
    rows = generate_default_schedule(c)
    years = [r["year"] for r in rows]
    assert years == [2026, 2027, 2028, 2029, 2030]
    for r in rows:
        assert r["optimizer_amount"] == 20_000.0
        assert r["override_amount"] is None
        assert r["locked"] is False


def test_no_year_s_draw_depends_on_a_prior_year_s_draw():
    """The actual regression: pull EVERY year's draw through withdraw_hsa_window
    in sequence, letting balances deplete exactly as a real projection would,
    and assert none of them spikes -- the cliff this bug produced was specific
    to the FINAL year, so the whole horizon must be checked, not just one."""
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 70_000.0}, consume_by="2032")
    rows = generate_default_schedule(c)
    c["hsa_withdrawal_mode"] = "optimize"
    c["hsa_schedule_by_year"] = {r["year"]: r for r in rows}
    bal = {"hsa1": 70_000.0}
    draws = []
    for year in range(2026, 2033):
        out = withdraw_hsa_window(c, bal, year)
        draws.append(out["amount"])
    expected = 70_000.0 / 7
    for d in draws:
        assert d == round(expected, 2), draws
    # The specific failure mode: the last year must NOT draw materially more
    # than every other year (it drew everything under the old formula).
    assert draws[-1] <= draws[0] * 1.01, (
        f"final year drew {draws[-1]}, first year drew {draws[0]} -- looks like the old cliff"
    )


def test_zero_balance_produces_no_schedule():
    c = _c(balances={"hsa1": 0.0}, consume_by="2030")
    assert generate_default_schedule(c) == []


def test_missing_hsa_ids_produces_no_schedule():
    c = _c(balances={"other_acct": 50_000.0}, hsa_ids=(), consume_by="2030")
    assert generate_default_schedule(c) == []


def test_deadline_before_plan_start_clamps_to_a_single_year():
    # resolve_consume_by_year's own _clamp never resolves earlier than
    # plan_start (see its docstring: "never earlier than the default, because
    # early is the unbounded failure") -- a deadline in the past relative to
    # plan_start clamps UP to plan_start, producing one valid year, not an
    # empty range.
    c = _c(plan_start=2026, balances={"hsa1": 50_000.0}, consume_by="2020")
    rows = generate_default_schedule(c)
    assert [r["year"] for r in rows] == [2026]
    assert rows[0]["optimizer_amount"] == 50_000.0


def test_missing_plan_start_produces_no_schedule():
    c = _c(balances={"hsa1": 50_000.0}, consume_by="2030")
    del c["plan_start"]
    assert generate_default_schedule(c) == []


def test_multiple_hsa_accounts_are_summed():
    c = _c(plan_start=2026, plan_end=2056,
           balances={"hsa1": 30_000.0, "hsa2": 20_000.0}, hsa_ids=("hsa1", "hsa2"),
           consume_by="2030")
    rows = generate_default_schedule(c)
    assert len(rows) == 5
    assert rows[0]["optimizer_amount"] == 10_000.0  # (30k+20k)/5


# --- _ensure_hsa_default_schedule: the build-time write path ----------------


def _import_ensure():
    from src.reporting.workbook_builder import _ensure_hsa_default_schedule
    return _ensure_hsa_default_schedule


def test_writes_a_file_when_optimize_mode_has_no_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    ensure = _import_ensure()
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 60_000.0}, consume_by="2028")
    c["hsa_withdrawal_mode"] = "optimize"
    c["hsa_schedule_rows"] = []
    ensure(c, "local")
    path = tmp_path / "input" / "client_hsa_schedule.csv"
    assert path.exists(), "expected a default schedule file to be written"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("year,optimizer_amount,override_amount,locked,note\n")
    assert "20000.0" in content  # 60k / 3 years (2026-2028)
    # Populated in-memory too, for THIS build to consume immediately.
    assert c["hsa_schedule_rows"], "in-memory schedule must be populated for this same build"
    assert c["hsa_schedule_by_year"][2026]["optimizer_amount"] == 20_000.0


def test_never_overwrites_an_existing_schedule_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "input").mkdir(parents=True)
    existing = "year,optimizer_amount,override_amount,locked,note\n2026,,9999,FALSE,user's own entry\n"
    path = tmp_path / "input" / "client_hsa_schedule.csv"
    path.write_text(existing, encoding="utf-8")

    ensure = _import_ensure()
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 60_000.0}, consume_by="2028")
    c["hsa_withdrawal_mode"] = "optimize"
    c["hsa_schedule_rows"] = []  # parse_client would normally have loaded the existing rows;
    # deliberately left empty here to prove the file-existence check (not the
    # in-memory rows check) is what prevents the overwrite.
    ensure(c, "local")
    assert path.read_text(encoding="utf-8") == existing, "an existing schedule file must never be overwritten"


def test_skips_entirely_when_mode_is_not_optimize(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    ensure = _import_ensure()
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 60_000.0}, consume_by="2028")
    c["hsa_withdrawal_mode"] = "smooth_window"
    c["hsa_schedule_rows"] = []
    ensure(c, "local")
    assert not (tmp_path / "input" / "client_hsa_schedule.csv").exists()


def test_skips_when_in_memory_rows_already_present(tmp_path, monkeypatch):
    """parse_client already loaded real rows from disk -- do not touch the
    file or the in-memory rows just because this ran."""
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    ensure = _import_ensure()
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 60_000.0}, consume_by="2028")
    c["hsa_withdrawal_mode"] = "optimize"
    c["hsa_schedule_rows"] = [{"year": 2026, "optimizer_amount": None, "override_amount": 111.0, "locked": False, "note": ""}]
    ensure(c, "local")
    assert not (tmp_path / "input" / "client_hsa_schedule.csv").exists()
    assert c["hsa_schedule_rows"] == [{"year": 2026, "optimizer_amount": None, "override_amount": 111.0, "locked": False, "note": ""}]


def test_write_failure_degrades_without_raising(tmp_path, monkeypatch):
    """A build must never fail just because the default schedule couldn't be
    written -- degrade to the per-year fallback instead."""
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    import src.reporting.workbook_builder as wb

    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(wb, "_ensure_hsa_default_schedule", wb._ensure_hsa_default_schedule)  # sanity import
    from src.workspace_context import workspace_file as real_workspace_file
    monkeypatch.setattr("src.workspace_context.workspace_file", _boom)

    ensure = _import_ensure()
    c = _c(plan_start=2026, plan_end=2056, balances={"hsa1": 60_000.0}, consume_by="2028")
    c["hsa_withdrawal_mode"] = "optimize"
    c["hsa_schedule_rows"] = []
    ensure(c, "local")  # must not raise
    assert c["hsa_schedule_rows"] == []


# --- allowlist regression, mirrors the existing wiring test's style --------


def test_default_schedule_note_field_is_quoted_csv_safe():
    """note contains no comma today, but the writer must still quote it --
    a defect-plant that removes quoting would only fail once a note does."""
    src = open("src/reporting/workbook_builder.py", encoding="utf-8").read()
    m = re.search(r'lines\.append\(f"\{r\[.year.\]\},\{r\[.optimizer_amount.\]\},,FALSE,\\"\{note\}\\""\)', src)
    assert m is not None, "expected the CSV writer line to double-quote the note field"
