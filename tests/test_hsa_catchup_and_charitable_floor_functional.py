"""Closed-form checks added with W3 (deduction block): HSA catch-up and the 0.5%-of-AGI charitable floor."""
from __future__ import annotations

from src.data_io import parse_hsa_policy


def test_hsa_catchup_is_kept_apart_from_the_indexed_base():
    p = parse_hsa_policy({}, 2026)
    # 8,750 x 6/12 + 4,400 x 6/12 = 6,575; the $1,000 age-55+ catch-up is its own fixed amount
    assert p['hsa_contrib_base'] == 6_575
    assert p['hsa_catchup'] == 1_000


def test_charitable_floor_starts_in_2026():
    from src.projection_stages.roth_conversion_and_agi_tax import charitable_agi_floor
    assert charitable_agi_floor(2025, 200_000.0) == 0.0
    assert charitable_agi_floor(2026, 200_000.0) == 1_000.0
