"""W3-03 / FIN-003: SALT is fed from the engine's computed state tax, not AGI x flat rate (MFJ closed-form cases)."""
from __future__ import annotations

import pytest

from src.projection_stages.roth_conversion_and_agi_tax import salt_deduction


def proxy(agi, rate=0.0495):
    return agi * rate


def test_2026_large_conversion_under_the_phase_down_delta_is_large():
    # MAGI 400k, property tax 12k, Illinois exempts the conversion so state tax is 3k, not 4.95% x 400k = 19.8k
    new = salt_deduction(2026, 400_000, 'MFJ', 3_000, 12_000)
    old = salt_deduction(2026, 400_000, 'MFJ', proxy(400_000), 12_000)
    assert new == pytest.approx(15_000)
    assert old == pytest.approx(31_800)
    assert old - new == pytest.approx(16_800)


def test_2026_at_or_above_620k_the_cap_is_at_its_floor_so_delta_is_zero():
    new = salt_deduction(2026, 650_000, 'MFJ', 3_000, 12_000)
    old = salt_deduction(2026, 650_000, 'MFJ', proxy(650_000), 12_000)
    assert new == old == pytest.approx(10_000)


def test_2030_homeowner_with_10k_property_tax_delta_is_zero():
    assert salt_deduction(2030, 300_000, 'MFJ', 2_000, 12_000) == salt_deduction(2030, 300_000, 'MFJ', proxy(300_000), 12_000) == pytest.approx(10_000)


def test_2030_renter_itemizer_delta_is_nonzero_and_bounded_by_10k_minus_actual():
    new = salt_deduction(2030, 500_000, 'MFJ', 4_000, 0.0)
    old = salt_deduction(2030, 500_000, 'MFJ', proxy(500_000), 0.0)
    assert new == pytest.approx(4_000) and old == pytest.approx(10_000)
    assert 0 < old - new <= 10_000 - 4_000
