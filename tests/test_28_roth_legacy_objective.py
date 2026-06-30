from pathlib import Path
import csv

from src.data_io import load_csv
from src.planning_engines import _roth_strategy_metrics

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_POLICY = ROOT / "input" / "client_policy.csv"
WORKSPACE_DATA = ROOT / "input" / "client_data.csv"


def test_client_policy_includes_legacy_roth_conversion_controls():
    with WORKSPACE_POLICY.open(newline="", encoding="utf-8-sig") as f:
        labels = {row["label"]: row for row in csv.DictReader(f) if row.get("label")}
    for label in [
        "legacy_objective_mode",
        "future_tax_rate_stress_pct",
        "future_tax_risk_weight",
        "inheritance_tax_burden_weight",
        "heir_ordinary_tax_rate_assumption_pct",
        "pre_tax_bequest_penalty_pct",
        "roth_bequest_preference_bonus_pct",
        "survivor_tax_risk_weight",
    ]:
        assert label in labels
    assert labels["legacy_objective_mode"]["value"] == "BALANCED"


def test_legacy_roth_conversion_controls_are_loaded_from_split_csvs():
    data = load_csv(WORKSPACE_DATA)
    roth = data["Withdrawal Policy"]["Roth Conversion"]
    assert roth["legacy_objective_mode"] == "BALANCED"
    assert roth["future_tax_rate_stress_pct"] == "10.00%"
    assert roth["heir_ordinary_tax_rate_assumption_pct"] == "24.00%"
    assert roth["roth_bequest_preference_bonus_pct"] == "5.00%"


def test_legacy_objective_penalizes_pretax_bequest_and_rewards_roth_bequest():
    base_rows = [
        {"year": 2030, "pretax_nw": 900000, "roth_nw": 100000, "trust_nw": 0, "hsa_nw": 0, "total_nw": 1000000, "total_tax": 0, "roth_conv": 0, "roth_wd": 0},
        {"year": 2040, "pretax_nw": 900000, "roth_nw": 100000, "trust_nw": 0, "hsa_nw": 0, "total_nw": 1000000, "total_tax": 0, "roth_conv": 0, "roth_wd": 0},
    ]
    roth_rows = [
        {"year": 2030, "pretax_nw": 100000, "roth_nw": 900000, "trust_nw": 0, "hsa_nw": 0, "total_nw": 1000000, "total_tax": 0, "roth_conv": 0, "roth_wd": 0},
        {"year": 2040, "pretax_nw": 100000, "roth_nw": 900000, "trust_nw": 0, "hsa_nw": 0, "total_nw": 1000000, "total_tax": 0, "roth_conv": 0, "roth_wd": 0},
    ]
    c = {
        "roth_legacy_objective_mode": "BALANCED",
        "roth_optimize_terminal_tax_rate": 0.24,
        "roth_optimize_terminal_weight": 1.0,
        "roth_optimize_tax_weight": 0.25,
        "roth_future_tax_rate_stress_pct": 0.10,
        "roth_future_tax_risk_weight": 0.35,
        "roth_inheritance_tax_burden_weight": 0.40,
        "roth_heir_ordinary_tax_rate_assumption": 0.32,
        "roth_pre_tax_bequest_penalty_pct": 0.25,
        "roth_bequest_preference_bonus_pct": 0.10,
        "roth_survivor_tax_risk_weight": 0.25,
        "h_death_yr": 2035,
        "w_death_yr": 2040,
    }
    pretax_metrics = _roth_strategy_metrics(c, base_rows)
    roth_metrics = _roth_strategy_metrics(c, roth_rows)
    assert pretax_metrics["pre_tax_inheritance_burden"] > roth_metrics["pre_tax_inheritance_burden"]
    assert roth_metrics["roth_legacy_preference_value"] > pretax_metrics["roth_legacy_preference_value"]
    assert roth_metrics["score"] > pretax_metrics["score"]
