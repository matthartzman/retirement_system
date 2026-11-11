"""Illinois estate tax method (attorney-confirmed): credit = min(2011(b) table on the estate less
$60,000, federal tentative tax with a $4,000,000 exclusion), solved with the interrelated deduction.

EXPECTED VALUES ARE HAND-DERIVED from the method (closed-form solutions of the interrelated
equation below), NOT matched to the Illinois Attorney General's calculator, which was not
available.  Replace with calculator figures if counsel supplies them.
"""
import pytest

from src.core import federal_tentative_tax, illinois_estate_tax, state_estate_tax

# phase-in (federal limit binds):   T = 0.4 * (G - T - 4M)            -> T = 0.4 * (G - 4M) / 1.4
# table binds (8.04M-9.04M band):   T = 786_800 + 0.144 * (G - T - 60k - 8.04M)
HAND_DERIVED = [
    (4_050_000.0, 0.4 * 50_000.0 / 1.4),
    (4_500_000.0, 0.4 * 500_000.0 / 1.4),
    (5_000_000.0, 0.4 * 1_000_000.0 / 1.4),
    (10_000_000.0, (786_800 + 0.144 * (10_000_000 - 60_000 - 8_040_000)) / 1.144),
]


@pytest.mark.parametrize("estate,expected", HAND_DERIVED)
def test_hand_derived_points(estate, expected):
    assert illinois_estate_tax(estate) == pytest.approx(expected, abs=0.5)


def test_zero_at_or_below_exclusion():
    assert illinois_estate_tax(0) == 0.0
    assert illinois_estate_tax(3_999_999) == 0.0
    assert illinois_estate_tax(4_000_000) == 0.0


def test_no_cliff_at_exclusion():
    assert illinois_estate_tax(4_000_001) < 1.0
    assert illinois_estate_tax(4_010_000) == pytest.approx(0.4 * 10_000 / 1.4, abs=0.5)


def test_monotonic_and_continuous():
    prev = 0.0
    estate = 3_900_000.0
    while estate <= 12_000_000.0:
        tax = illinois_estate_tax(estate)
        assert tax >= prev - 0.01
        assert tax - prev <= 0.5 * 25_000.0  # marginal rate well under 50%: no jumps
        assert tax < estate - 4_000_000.0 + 1.0 or estate <= 4_000_000.0
        prev = tax
        estate += 25_000.0


def test_federal_tentative_tax_schedule():
    assert federal_tentative_tax(1_000_000) == pytest.approx(345_800)
    assert federal_tentative_tax(4_000_000) == pytest.approx(345_800 + 0.4 * 3_000_000)
    assert federal_tentative_tax(5_000_000, 4_000_000) == pytest.approx(400_000)
    assert federal_tentative_tax(3_000_000, 4_000_000) == 0.0


def test_dispatch_uses_new_method():
    tax, status = state_estate_tax("Illinois", 4_050_000.0)
    assert status == "computed"
    assert tax == pytest.approx(HAND_DERIVED[0][1], abs=0.5)
