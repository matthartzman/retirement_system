from pathlib import Path


def test_after_tax_helper_models_taxable_cap_gain_components():
    from src.after_tax import estimate_after_tax_terminal_net_worth

    c = {
        "taxable_ids": ["Taxable_Brokerage"],
        "pre_tax_ids": ["IRA"],
        "roth_target_rate": 0.24,
        "trust_gain_fraction": 0.50,
        "plan_start": 2026,
        "plan_end": 2056,
        "filing_status": "MFJ",
        "state": "Illinois",
        "model_niit": True,
        "ltcg_0_top": 96700,
        "ltcg_15_top": 600050,
        "irmaa_inflator": 0.02,
    }
    terminal = {
        "year": 2056,
        "total_nw": 2_000_000,
        "pretax_nw": 500_000,
        "trust_nw": 400_000,
        "Taxable_Brokerage": 400_000,
        "taxable_inc": 150_000,
        "agi": 180_000,
    }
    result = estimate_after_tax_terminal_net_worth(c, terminal)
    assert result["terminal_deferred_pretax_tax"] == 120_000
    assert result["terminal_taxable_unrealized_gain_est"] == 200_000
    assert result["terminal_deferred_taxable_cap_gain_tax"] > 0
    assert result["terminal_deferred_tax_total"] > result["terminal_deferred_pretax_tax"]
    assert result["after_tax_terminal_nw"] < 1_880_000


def test_plan_summary_exposes_terminal_cap_gain_fields():
    src = Path("src/reporting/workbook_builder.py").read_text(encoding="utf-8")
    assert "terminal_deferred_taxable_cap_gain_tax" in src
    assert "terminal_taxable_unrealized_gain_est" in src
    assert "terminal_taxable_basis_est" in src
    assert "estimate_after_tax_terminal_net_worth" in src


def test_frontend_after_tax_description_mentions_capital_gains():
    js = Path("frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "deferred capital-gains tax on taxable brokerage assets" in js
    assert "summary.terminal_deferred_tax_total" in js


def test_roth_strategy_metrics_uses_after_tax_helper_for_taxable_gains():
    src = Path("src/planning_engines.py").read_text(encoding="utf-8")
    assert "estimate_after_tax_terminal_net_worth" in src
