"""The gateway's per-user plan limits reach each worker as environment variables, and cannot be set by a user."""
from __future__ import annotations

import pytest

from src import plan_limits
from src.gateway.supervisor import Supervisor, SupervisorConfig


def _spec(tmp_path, **kw):
    sup = Supervisor(SupervisorConfig(data_root=tmp_path, **kw), launcher=None)
    return sup._launch_spec(7, sup.workspace(7), "tok")


def test_limits_are_passed_to_the_worker(tmp_path):
    spec = _spec(tmp_path, max_plans_per_user=10, user_disk_quota_mb=1024)
    assert spec.env[plan_limits.MAX_PLANS_ENV] == "10"
    assert spec.env[plan_limits.QUOTA_ENV] == "1024"


def test_zero_or_none_sets_no_limit_variables(tmp_path):
    spec = _spec(tmp_path, max_plans_per_user=0, user_disk_quota_mb=None)
    assert plan_limits.MAX_PLANS_ENV not in spec.env and plan_limits.QUOTA_ENV not in spec.env


def test_defaults_are_ten_plans_and_1024_mb(tmp_path):
    cfg = SupervisorConfig(data_root=tmp_path)
    assert (cfg.max_plans_per_user, cfg.user_disk_quota_mb) == (10, 1024)


def test_an_operator_env_value_cannot_override_the_gateway_setting(tmp_path):
    spec = _spec(tmp_path, max_plans_per_user=3, extra_env={plan_limits.MAX_PLANS_ENV: "999"})
    assert spec.env[plan_limits.MAX_PLANS_ENV] == "3"


def test_gateway_cli_flags_exist():
    from src.gateway import server

    text = open(server.__file__, encoding="utf-8").read()
    assert "--max-plans-per-user" in text and "--user-disk-quota-mb" in text
