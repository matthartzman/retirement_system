"""Wave 3.6 (system review 2026-08-04, finding C4 /
mortality-gaussian-not-life-table, re-assessed effort M -> L in §2.5):
replaces the truncated-normal mortality sampler (floored at age 70, near-zero
probability of death before 80) with an SSA/SOA-table-derived, age-varying
hazard curve, calibrated to the household's own configured mortality_age.

§2.5's key finding was that the panel-cited scalar sample_death_year() is
NOT the only sampler -- _mc_vectorized_death_years() is a second,
independent copy that actually produces the headline Monte Carlo success
rate. Both are tested here explicitly, per the acceptance criterion the
system review itself specified.
"""
from __future__ import annotations

import random

import numpy as np

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import (
    _mc_vectorized_death_years,
    _mortality_qx,
    _mortality_qx_table,
    _population_median_age,
    sample_death_year,
)

from conftest import TEST_INPUT_DIR


def sample_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    return ensure_engine_config(c, source="test")


def test_mortality_table_loads_and_covers_a_realistic_age_range():
    table = _mortality_qx_table()
    assert table
    assert min(table.keys()) <= 50
    assert max(table.keys()) >= 100


def test_qx_increases_monotonically_with_age():
    for sex_idx in (0, 1):
        prev = 0.0
        for age in range(50, 105, 5):
            qx = _mortality_qx(age, sex_idx)
            assert qx >= prev, f"qx should not decrease with age (sex {sex_idx}, age {age})"
            prev = qx


def test_scalar_sampler_can_produce_death_before_age_70():
    # The exact defect this wave fixes: the old model had a hard floor at 70
    # (max(70.0, ...)), making death before 70 impossible regardless of input.
    c = sample_config()
    rng = random.Random(7)
    h_dob = c["members"][0]["dob_yr"]
    ages = [sample_death_year(c, 0, rng) - h_dob for _ in range(3000)]
    assert min(ages) < 70, "death before 70 should be possible, not floored out"


def test_scalar_sampler_median_tracks_configured_mortality_age():
    c = sample_config()
    rng = random.Random(11)
    h_dob = c["members"][0]["dob_yr"]
    configured = float(c["members"][0].get("mortality_age", 92) or 92)
    ages = sorted(sample_death_year(c, 0, rng) - h_dob for _ in range(4000))
    median = ages[len(ages) // 2]
    assert abs(median - configured) <= 3, "calibration should track the user's own longevity input"


def test_vectorized_sampler_can_produce_death_before_age_70():
    # The acceptance criterion the system review itself specified: the fix is
    # not complete until the VECTORIZED path also draws from the table, not
    # just the scalar one the original panel review cited.
    c = sample_config()
    rng = np.random.default_rng(7)
    h, w, both = _mc_vectorized_death_years(c, rng, 5000)
    h_dob = c["members"][0]["dob_yr"]
    h_ages = h - h_dob
    assert (h_ages < 70).sum() > 0, "vectorized MC death-year sampler must also allow death before 70"


def test_vectorized_and_scalar_samplers_agree_on_median_within_noise():
    c = sample_config()
    rng_np = np.random.default_rng(13)
    h, w, both = _mc_vectorized_death_years(c, rng_np, 5000)
    h_dob = c["members"][0]["dob_yr"]
    vec_median = float(np.median(h - h_dob))

    rng_scalar = random.Random(13)
    scalar_ages = sorted(sample_death_year(c, 0, rng_scalar) - h_dob for _ in range(5000))
    scalar_median = scalar_ages[len(scalar_ages) // 2]
    assert abs(vec_median - scalar_median) <= 2, "the two independent samplers must agree, not silently diverge"
