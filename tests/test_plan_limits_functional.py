"""Per-user plan-count cap and disk quota (multi-user multiple-plans design, section 5)."""
from __future__ import annotations

import pytest

from src import plan_limits, plan_registry


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(plan_limits.MAX_PLANS_ENV, raising=False)
    monkeypatch.delenv(plan_limits.QUOTA_ENV, raising=False)
    plan_registry.invalidate()
    plan_limits.invalidate()
    return tmp_path


def _register(ws, n, kind="user"):
    for i in range(n):
        f = ws / f"p{kind}{i}.rpx"
        f.write_bytes(b"x")
        plan_registry.register_plan_file(f, name=f"{kind} {i}", kind=kind)


def test_unset_limits_mean_unlimited(ws):
    _register(ws, 3)
    plan_limits.check_can_add_plan(extra_bytes=10**12)
    plan_limits.check_can_build()


def test_plan_count_cap_refuses_at_the_limit(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, "2")
    plan_limits.check_can_add_plan()  # only the workspace plan.rpx, registered on first use
    _register(ws, 1, kind="case")
    with pytest.raises(plan_limits.PlanLimitError, match="2 plans"):
        plan_limits.check_can_add_plan()


def test_demo_plan_is_not_counted(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, "2")
    _register(ws, 2, kind="demo")
    plan_limits.check_can_add_plan()


def test_zero_means_unlimited(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, "0")
    monkeypatch.setenv(plan_limits.QUOTA_ENV, "0")
    _register(ws, 4)
    plan_limits.check_can_add_plan(extra_bytes=10**12)


def test_quota_counts_the_workspace_and_the_new_bytes(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.QUOTA_ENV, "1")  # 1 MiB
    (ws / "big.bin").write_bytes(b"0" * 600_000)
    plan_limits.invalidate()
    plan_limits.check_can_add_plan(extra_bytes=100_000)
    with pytest.raises(plan_limits.PlanLimitError, match="disk"):
        plan_limits.check_can_add_plan(extra_bytes=600_000)


def test_build_start_refused_only_when_already_over_quota(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.QUOTA_ENV, "1")
    (ws / "big.bin").write_bytes(b"0" * 900_000)
    plan_limits.invalidate()
    plan_limits.check_can_build()
    (ws / "big2.bin").write_bytes(b"0" * 300_000)
    plan_limits.invalidate()
    with pytest.raises(plan_limits.PlanLimitError):
        plan_limits.check_can_build()


def test_usage_reports_limits_and_orphans(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, "10")
    monkeypatch.setenv(plan_limits.QUOTA_ENV, "1024")
    _register(ws, 2)
    (ws / "saved_plans").mkdir()
    (ws / "saved_plans" / "old.rpx").write_bytes(b"0" * 2048)
    plan_limits.invalidate()
    u = plan_limits.usage()
    assert u["plan_count"] == 3  # 2 + the workspace plan.rpx
    assert u["max_plans"] == 10 and u["disk_quota_mb"] == 1024
    assert u["disk_used_mb"] >= 0 and u["orphan_mb"] > 0


def test_garbage_env_values_fail_safe_to_unlimited_not_zero_plans(ws, monkeypatch):
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, "ten")
    assert plan_limits.max_plans() == 0
