"""Transaction processor facade — public API for spending_tracker functions.

This module provides a clean interface to transaction loading, budget management,
taxonomy operations, and spending categorization without exposing internal
spending_tracker implementation details.

Functions:
- load_transactions: Load transaction records for a given year
- load_transactions_extended: Load transactions with category mapping
- load_budget: Load annual spending budget by category
- save_budget: Save budget modifications
- load_category_map: Load category ID to label mapping
- save_category_map: Save category mapping updates
- load_taxonomy: Load complete spending taxonomy (tracking types, groups, categories)
- taxonomy_flat: Get flattened taxonomy for UI rendering
- group_actuals: Group and sum transactions by category
- budget_by_group: Get aggregated budget by group
- load_mapping_rules: Load category mapping/classification rules
- save_mapping_rules: Save mapping rule updates
- apply_mapping_rules: Apply rules to categorize transactions
"""

from .spending_tracker import (
    load_transactions,
    load_transactions_extended,
    load_budget,
    save_budget,
    load_category_map,
    save_category_map,
    load_taxonomy,
    taxonomy_flat,
    group_actuals,
    budget_by_group,
    load_mapping_rules,
    save_mapping_rules,
    apply_mapping_rules,
)

__all__ = [
    'load_transactions',
    'load_transactions_extended',
    'load_budget',
    'save_budget',
    'load_category_map',
    'save_category_map',
    'load_taxonomy',
    'taxonomy_flat',
    'group_actuals',
    'budget_by_group',
    'load_mapping_rules',
    'save_mapping_rules',
    'apply_mapping_rules',
]
