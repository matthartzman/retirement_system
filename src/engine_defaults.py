"""Code defaults of the engine knobs that used to live in ``system_config.csv`` (WP8.1).

Rebalancing, Asset Class Assumptions, Asset Correlations, Annuity Calibration and Plan
Settings are plan settings: a plan row of the same key wins, and a key the plan does not hold
reads the default below (``with_engine_defaults``, applied where the engine view of the plan is
built: ``config_backend.load_active_config`` and ``data_io.parse_client``). The values are the
ones the CSV shipped, so a plan without these rows computes exactly as before.
"""
from __future__ import annotations

from typing import Dict

SettingMap = Dict[str, Dict[str, Dict[str, str]]]

# (section, subsection, label, value, units, notes)
ENGINE_DEFAULT_ROWS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ('Plan Settings', 'Tax Detail', 'model_niit', 'TRUE', 'boolean', 'Apply 3.8% Net Investment Income Tax above MAGI threshold'),
    ('Plan Settings', 'Estate', 'model_state_estate_tax', 'TRUE', 'boolean', 'Model residence-state estate tax in addition to federal'),
    ('Asset Class Assumptions', 'Global', 'capital_market_assumption_mode', 'PRESET', 'choice', 'PRESET uses built-in horizon/preset assumptions; CUSTOM_FILE reads capital_market_assumptions.csv. Advanced users only.'),
    ('Asset Class Assumptions', 'Global', 'capital_market_assumption_horizon_years', '30', 'years', 'Planning horizon for allocation optimizer assumptions. Supported: 1, 3, 5, 10, 20, 25, 30. 30 is the long-term baseline. Ignored when capital_market_assumption_horizon_source is auto_from_withdrawals.'),
    ('Asset Class Assumptions', 'Global', 'capital_market_assumption_horizon_source', 'manual', 'choice', "manual (default) uses horizon_years above. auto_from_withdrawals derives the effective horizon from this household's own projected withdrawal schedule instead."),
    ('Asset Class Assumptions', 'Global', 'capital_market_assumption_preset', 'BASELINE', 'choice', 'CONSERVATIVE, BASELINE, or AGGRESSIVE. This shifts return/volatility assumptions before per-asset overrides.'),
    ('Asset Class Assumptions', 'Global', 'use_custom_capital_market_file', 'NO', 'yes/no', 'YES reads expert assumptions from custom_capital_market_file. Keep NO unless using a reviewed capital-market assumptions CSV.'),
    ('Asset Class Assumptions', 'Global', 'custom_capital_market_file', 'capital_market_assumptions.csv', 'path', 'Expert CSV path with horizon_years,preset,asset_class,expected_return,volatility,stock_index_correlation.'),
    ('Asset Class Assumptions', 'Global', 'correlation_assumption_mode', 'PRESET', 'choice', 'PRESET uses low/moderate/high/stress correlation presets. ADVANCED also applies Asset Correlations rows. CUSTOM_FILE also reads asset_correlations.csv.'),
    ('Asset Class Assumptions', 'Global', 'correlation_preset', 'MODERATE', 'choice', 'LOW, MODERATE, HIGH, or STRESS. Higher/stress correlations reduce diversification benefits.'),
    ('Asset Class Assumptions', 'Global', 'use_custom_correlations_file', 'NO', 'yes/no', 'YES reads expert pairwise correlations from custom_correlations_file.'),
    ('Asset Class Assumptions', 'Global', 'custom_correlations_file', 'asset_correlations.csv', 'path', 'Expert CSV path with horizon_years,preset,asset_class_a,asset_class_b,correlation.'),
    ('Asset Class Assumptions', 'US Large Cap', 'expected_return', '10.00%', 'pct', 'Default 10.0%; optimizer return input for US Large Cap. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'US Large Cap', 'volatility', '15.00%', 'pct', 'Default 15.0%; optimizer risk input for US Large Cap.'),
    ('Asset Class Assumptions', 'US Mid Cap', 'expected_return', '10.50%', 'pct', 'Default 10.5%; optimizer return input for US Mid Cap. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'US Mid Cap', 'volatility', '18.00%', 'pct', 'Default 18.0%; optimizer risk input for US Mid Cap.'),
    ('Asset Class Assumptions', 'US Small Cap', 'expected_return', '11.50%', 'pct', 'Default 11.5%; optimizer return input for US Small Cap. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'US Small Cap', 'volatility', '22.00%', 'pct', 'Default 22.0%; optimizer risk input for US Small Cap.'),
    ('Asset Class Assumptions', 'International', 'expected_return', '8.00%', 'pct', 'Default 8.0%; optimizer return input for International. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'International', 'volatility', '17.00%', 'pct', 'Default 17.0%; optimizer risk input for International.'),
    ('Asset Class Assumptions', 'Emerging Markets', 'expected_return', '9.00%', 'pct', 'Default 9.0%; optimizer return input for Emerging Markets. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Emerging Markets', 'volatility', '22.00%', 'pct', 'Default 22.0%; optimizer risk input for Emerging Markets.'),
    ('Asset Class Assumptions', 'Commodities', 'expected_return', '5.00%', 'pct', 'Default 5.0%; optimizer return input for Commodities. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Commodities', 'volatility', '18.00%', 'pct', 'Default 18.0%; optimizer risk input for Commodities.'),
    ('Asset Class Assumptions', 'Bonds', 'expected_return', '4.00%', 'pct', 'Default 4.0%; optimizer return input for Bonds. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Bonds', 'volatility', '5.00%', 'pct', 'Default 5.0%; optimizer risk input for Bonds.'),
    ('Asset Class Assumptions', 'Short-Term Bonds', 'expected_return', '3.50%', 'pct', 'Default 3.5%; optimizer return input for Short-Term Bonds. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Short-Term Bonds', 'volatility', '3.00%', 'pct', 'Default 3.0%; optimizer risk input for Short-Term Bonds.'),
    ('Asset Class Assumptions', 'TIPS', 'expected_return', '4.00%', 'pct', 'Default 4.0%; optimizer return input for TIPS. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'TIPS', 'volatility', '5.00%', 'pct', 'Default 5.0%; optimizer risk input for TIPS.'),
    ('Asset Class Assumptions', 'Municipal Bonds', 'expected_return', '3.50%', 'pct', 'Default 3.5%; optimizer return input for Municipal Bonds. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Municipal Bonds', 'volatility', '4.50%', 'pct', 'Default 4.5%; optimizer risk input for Municipal Bonds.'),
    ('Asset Class Assumptions', 'Managed Futures', 'expected_return', '6.00%', 'pct', 'Default 6.0%; optimizer return input for Managed Futures. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Managed Futures', 'volatility', '10.00%', 'pct', 'Default 10.0%; optimizer risk input for Managed Futures.'),
    ('Asset Class Assumptions', 'Private Credit', 'expected_return', '7.00%', 'pct', 'Default 7.0%; optimizer return input for Private Credit. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Private Credit', 'volatility', '8.00%', 'pct', 'Default 8.0%; optimizer risk input for Private Credit.'),
    ('Asset Class Assumptions', 'REITs', 'expected_return', '8.00%', 'pct', 'Default 8.0%; optimizer return input for REITs. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'REITs', 'volatility', '19.00%', 'pct', 'Default 19.0%; optimizer risk input for REITs.'),
    ('Asset Class Assumptions', 'Cash', 'expected_return', '2.00%', 'pct', 'Default 2.0%; optimizer return input for Cash. Affects recommended allocation only.'),
    ('Asset Class Assumptions', 'Cash', 'volatility', '1.00%', 'pct', 'Default 1.0%; optimizer risk input for Cash.'),
    ('Asset Correlations', 'US Equity|Emerging Markets', 'correlation', '72%', 'pct', 'Default example correlation between US Equity and Emerging Markets. Edit only in advanced/expert mode.'),
    ('Asset Correlations', 'US Equity|Bonds', 'correlation', '-20%', 'pct', 'Default example correlation between US Equity and Bonds. Edit only in advanced/expert mode.'),
    ('Asset Correlations', 'US Equity|Managed Futures', 'correlation', '-5%', 'pct', 'Default example correlation between US Equity and Managed Futures. Edit only in advanced/expert mode.'),
    ('Asset Correlations', 'Bonds|TIPS', 'correlation', '55%', 'pct', 'Default example correlation between Bonds and TIPS. Edit only in advanced/expert mode.'),
    ('Asset Correlations', 'Private Credit|US Equity', 'correlation', '45%', 'pct', 'Default example correlation between Private Credit and US Equity. Edit only in advanced/expert mode.'),
    ('Rebalancing', 'Optimization', 'trade_optimizer_mode', 'GLOBAL_TAX_AWARE', 'choice', 'GLOBAL_TAX_AWARE solves household-level drift/tax/location tradeoffs; HEURISTIC uses the prior account-by-account engine.'),
    ('Rebalancing', 'Optimization', 'max_tax_cost_bps', '25', 'bps', 'Maximum estimated realized-tax drag for ordinary taxable sales before deferral, unless drift/policy allows. 25 bps = 0.25% of sale amount.'),
    ('Rebalancing', 'Optimization', 'min_trade_amount', '500', 'USD', 'Suppresses small/noisy trades and false precision.'),
    ('Rebalancing', 'Optimization', 'max_turnover_pct', '20.00%', 'pct', 'Maximum sell turnover recommended in one workbook cycle; controls excessive trading.'),
    ('Rebalancing', 'Optimization', 'wash_sale_policy', 'FLAG_ONLY', 'choice', 'FLAG_ONLY adds review notes; AVOID_SAME_SYMBOL/STRICT_AVOID are conservative policy labels for review workflows.'),
    ('Rebalancing', 'Optimization', 'allow_taxable_gain_sales', 'DRIFT_THRESHOLD', 'choice', 'NEVER, DRIFT_THRESHOLD, WITHIN_BUDGET, or ALWAYS. Controls whether allocation benefit can justify taxable gains.'),
    ('Rebalancing', 'Optimization', 'asset_location_strength', 'BALANCED', 'choice', 'LIGHT/BALANCED/STRONG controls how aggressively Roth growth, pre-tax income, and taxable tax-efficient equity placement are preferred.'),
    ('Rebalancing', 'Optimization', 'solver_fallback_policy', 'HEURISTIC', 'choice', 'If the global optimizer is infeasible/unavailable, HEURISTIC falls back to the previous tax-aware trade engine.'),
    ('Rebalancing', 'Risk Controls', 'max_account_single_asset_pct', '45.00%', 'pct', 'Caps one ETF/fund within an account to reduce concentration caused by global optimization.'),
    ('Rebalancing', 'Risk Controls', 'max_roth_high_growth_pct', '85.00%', 'pct', 'Caps growth/volatile sleeves inside Roth so tax efficiency does not create an uncomfortable Roth risk tilt.'),
    ('Rebalancing', 'Risk Controls', 'max_pre_tax_fixed_income_pct', '85.00%', 'pct', 'Caps fixed-income concentration in pre-tax accounts to reduce future RMD/growth concentration risk.'),
    ('Rebalancing', 'Risk Controls', 'max_trades_per_account', '8', 'count', 'Limits recommendation complexity and operational burden.'),
    ('Rebalancing', 'Risk Controls', 'legacy_gain_deferral_pct', '20.00%', 'pct', 'Large embedded-gain taxable positions above this share are deferred unless settings are loosened.'),
    ('Rebalancing', 'Tax-aware Trades', 'taxable_gain_budget_annual', '2500', 'USD', 'Estimated annual tax-cost budget for recommended taxable gain sales; controls income timing/IRMAA/NIIT surprises.'),
    ('Rebalancing', 'Tax-aware Trades', 'ltcg_rate', '15.00%', 'pct', 'Long-term capital gains tax-rate input for trade optimization; adjust for your marginal situation.'),
    ('Rebalancing', 'Tax-aware Trades', 'max_tax_drag_pct', '1.50%', 'pct', 'Existing lot-level taxable sell screen limit used by the fallback and global engines.'),
    ('Rebalancing', 'Tax-aware Trades', 'force_taxable_sell_drift_pct', '8.00%', 'pct', 'Allows taxable gains when portfolio drift is large enough to outweigh deferral.'),
    ('Rebalancing', 'Tax-aware Trades', 'taxable_review_drift_pct', '5.00%', 'pct', 'Review threshold for moderate taxable drift.'),
    ('Rebalancing', 'Objective Weights', 'drift_penalty_per_dollar', '1.0', 'decimal', 'Higher values prioritize target allocation completeness over tax/turnover/location penalties.'),
    ('Rebalancing', 'Objective Weights', 'turnover_penalty_per_dollar', '0.02', 'decimal', 'Higher values suppress trades unless drift/location/tax-loss benefits justify turnover.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg1_age_start', '0', 'years', 'Segment 1 start age of the carrier-agnostic annuity purchase-rate curve.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg1_age_end', '68', 'years', 'Segment 1 end age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg1_base_rate', '5.00%', 'pct', 'Segment 1 base purchase rate.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg1_slope', '0.00%', 'pct', 'Segment 1 rate slope per year of age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg2_age_start', '68', 'years', 'Segment 2 start age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg2_age_end', '75', 'years', 'Segment 2 end age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg2_base_rate', '5.00%', 'pct', 'Segment 2 base purchase rate.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg2_slope', '0.20%', 'pct', 'Segment 2 rate slope per year of age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg3_age_start', '75', 'years', 'Segment 3 start age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg3_age_end', '85', 'years', 'Segment 3 end age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg3_base_rate', '6.40%', 'pct', 'Segment 3 base purchase rate.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg3_slope', '0.50%', 'pct', 'Segment 3 rate slope per year of age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg4_age_start', '85', 'years', 'Segment 4 start age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg4_age_end', '95', 'years', 'Segment 4 end age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg4_base_rate', '11.40%', 'pct', 'Segment 4 base purchase rate.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg4_slope', '0.70%', 'pct', 'Segment 4 rate slope per year of age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg5_age_start', '95', 'years', 'Segment 5 start age.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg5_age_end', '999', 'years', 'Segment 5 end age (999 = no upper bound; covers remaining lifetime).'),
    ('Annuity Calibration', 'Purchase Rate', 'seg5_base_rate', '18.40%', 'pct', 'Segment 5 base purchase rate.'),
    ('Annuity Calibration', 'Purchase Rate', 'seg5_slope', '1.50%', 'pct', 'Segment 5 rate slope per year of age.'),
    ('Annuity Calibration', 'Reserve Decay', 'reserve_decay_rate', '0.975', 'decimal', 'Annual reserve decay factor applied for the first reserve_decay_period years.'),
    ('Annuity Calibration', 'Reserve Decay', 'reserve_decay_period', '6', 'years', 'Number of years the initial reserve decay factor applies.'),
    ('Annuity Calibration', 'Reserve Decay', 'mortality_credit_boost', '1.29', 'decimal', 'Multiplier applied to the reserve at mortality-credit onset.'),
    ('Annuity Calibration', 'Reserve Decay', 'post_credit_decay_rate', '0.96', 'decimal', 'Annual reserve decay factor applied after the mortality-credit boost.'),
    ('Annuity Calibration', 'Reserve Decay', 'post_credit_decay_period', '16', 'years', 'Years the post-credit decay factor applies before the late-life growth phase.'),
    ('Annuity Calibration', 'Reserve Decay', 'late_life_growth_rate', '1.07', 'decimal', 'Annual reserve growth factor applied in the late-life transition phase.'),
)
ENGINE_SECTIONS: frozenset[str] = frozenset(r[0] for r in ENGINE_DEFAULT_ROWS)


def engine_defaults() -> SettingMap:
    """The default engine knobs as section -> subsection -> label -> value."""
    out: SettingMap = {}
    for sec, sub, lbl, value, _units, _notes in ENGINE_DEFAULT_ROWS:
        out.setdefault(sec, {}).setdefault(sub, {})[lbl] = value
    return out


def with_engine_defaults(data: SettingMap) -> SettingMap:
    """A copy of ``data`` with every engine knob the plan does not hold filled from the defaults."""
    merged: SettingMap = {sec: {sub: dict(vals) for sub, vals in subs.items()} for sec, subs in data.items()}
    for sec, sub, lbl, value, _units, _notes in ENGINE_DEFAULT_ROWS:
        merged.setdefault(sec, {}).setdefault(sub, {}).setdefault(lbl, value)
    return merged


def engine_default_row(section: str, subsection: str, label: str) -> tuple[str, str, str, str, str, str] | None:
    for row in ENGINE_DEFAULT_ROWS:
        if row[:3] == (section, subsection, label):
            return row
    return None
