"""Asset allocation helpers and recommendation engine.

This module provides allocation-focused workbook functionality:
- Asset class bucket definitions and ETF candidates
- Tax-aware rebalance trade optimization
- Allocation-drift analysis and recommendation scoring
- build_sheet4: Asset Allocation & Rebalance Recommendation

Includes tax-loss harvesting analysis, account-location fit scoring, and
trade-execution guidance with wash-sale flagging and symbol substitution.

Future: This facade will import from sheets_summary.py until code is physically moved.
Once the physical split is complete, this will be the canonical source for allocation logic.
"""

from .sheets_summary import (
    ASSET_ALLOCATION_BUCKET_MAP,
    build_sheet4,
    _candidate_symbols,
    _hide_zero_before_after_row,
    _status_for_bucket,
    _after_status_for_total_mix,
    _workbook_pricing_source_label,
    _safe_float,
    _trade_tax_rates,
    _lot_purchase_year,
    _lot_is_long_term,
    _estimate_taxable_sale,
    _lot_guidance_summary,
    _taxable_sell_decision,
    _wash_sale_review_note,
    _is_cash_position_trade,
    _projected_account_cash_after_trades,
    _append_cash_movement_rows,
    _rebalance_settings,
    _bucket_location_fit,
    _bucket_is_high_growth,
    _bucket_is_fixed_income,
    _location_weight,
)

__all__ = [
    'ASSET_ALLOCATION_BUCKET_MAP',
    'build_sheet4',
    '_candidate_symbols',
    '_hide_zero_before_after_row',
    '_status_for_bucket',
    '_after_status_for_total_mix',
    '_workbook_pricing_source_label',
    '_safe_float',
    '_trade_tax_rates',
    '_lot_purchase_year',
    '_lot_is_long_term',
    '_estimate_taxable_sale',
    '_lot_guidance_summary',
    '_taxable_sell_decision',
    '_wash_sale_review_note',
    '_is_cash_position_trade',
    '_projected_account_cash_after_trades',
    '_append_cash_movement_rows',
    '_rebalance_settings',
    '_bucket_location_fit',
    '_bucket_is_high_growth',
    '_bucket_is_fixed_income',
    '_location_weight',
]
