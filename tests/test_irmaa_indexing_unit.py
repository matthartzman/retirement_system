import pytest
from src import tax_kernel as tk
from src import taxes as _td

VY = _td.IRMAA_TIERS_VALUE_YEAR          # 2025
C = {"plan_start": 2026, "inf": 0.03, "med_inf": 0.055, "partd_inf": 0.0125}

def _round(x, step):
    return round(x / step) * step

def test_threshold_is_cpi_indexed_from_value_year_and_rounded():
    c = dict(C, irmaa_inflator=0.10)                      # must be ignored
    n = 2036 - VY
    assert tk.irmaa_threshold(c, "MFJ", 0, 2036) == _round(212000 * 1.03 ** n, 2000)
    assert tk.irmaa_threshold(c, "Single", 0, 2036) == _round(106000 * 1.03 ** n, 1000)

def test_top_tier_frozen_through_2027_then_indexed():
    top = len(_td.IRMAA_TIERS_BASE_YEAR["MFJ"]) - 1
    assert tk.irmaa_threshold(C, "MFJ", top, 2027) == 750000
    assert tk.irmaa_threshold(C, "MFJ", top, 2030) == _round(750000 * 1.03 ** 3, 2000)

def test_surcharge_dollars_grow_with_medicare_rates_rounded_to_dimes():
    _, pb, pd = _td.IRMAA_TIERS_BASE_YEAR["MFJ"][-1]
    n = 2036 - VY
    want = (round(pb * 1.055 ** n, 1) + round(pd * 1.0125 ** n, 1)) * 2 * 12
    assert tk.irmaa_surcharge(10_000_000, 2036, 2, "MFJ", C) == pytest.approx(want)

def test_monte_carlo_path_bridged_from_value_year():
    c = dict(C, inflation_index_by_year={2030: 1.5}, medical_index_by_year={2030: 2.0})
    assert tk.irmaa_threshold_factor(c, 2030) == pytest.approx(1.03 ** (2026 - VY) * 1.5)
    assert tk.irmaa_partb_factor(c, 2030) == pytest.approx(1.055 ** (2026 - VY) * 2.0)
    assert tk.irmaa_partd_factor(c, 2030) == pytest.approx(1.0125 ** (2030 - VY))

def test_tier_boundaries_use_rounded_threshold():
    t = tk.irmaa_threshold(C, "MFJ", 0, 2036)
    assert tk.irmaa_tier(t, 2036, "MFJ", C) == 0          # statute: "more than"
    assert tk.irmaa_tier(t + 1, 2036, "MFJ", C) == 1
