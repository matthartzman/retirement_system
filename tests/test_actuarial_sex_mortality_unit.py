"""FIN-012: the mortality samplers read a per-member actuarial_sex field.

Blank keeps the legacy positional choice (member 1 -> male column, member 2 ->
female column), so existing plans are unchanged.
"""
import random

import numpy as np

from src.engine_kernels import _member_sex_idx, sample_death_year
from src.planning_engines import _mc_vectorized_sample_death_ages


def _plan(sex1="", sex2=""):
    return {
        "plan_start": 2026,
        "members": [
            {"dob_yr": 1960, "mortality_age": 88, "actuarial_sex": sex1},
            {"dob_yr": 1960, "mortality_age": 88, "actuarial_sex": sex2},
        ],
    }


def test_blank_field_keeps_positional_default():
    assert _member_sex_idx({}, 0) == 0
    assert _member_sex_idx({"actuarial_sex": ""}, 1) == 1
    assert _member_sex_idx({"actuarial_sex": "unknown"}, 0) == 0


def test_explicit_field_overrides_position():
    assert _member_sex_idx({"actuarial_sex": "female"}, 0) == 1
    assert _member_sex_idx({"actuarial_sex": "Male"}, 1) == 0


def test_scalar_sampler_member_one_female_equals_member_two_default():
    # Same dob/median/seed: a female member 1 must draw exactly what a
    # positional-female member 2 draws.
    as_member1 = [sample_death_year(_plan("female"), 0, random.Random(s)) for s in range(200)]
    as_member2 = [sample_death_year(_plan(), 1, random.Random(s)) for s in range(200)]
    assert as_member1 == as_member2


def test_scalar_sampler_default_unchanged():
    male_default = [sample_death_year(_plan(), 0, random.Random(s)) for s in range(200)]
    male_explicit = [sample_death_year(_plan("male"), 0, random.Random(s)) for s in range(200)]
    assert male_default == male_explicit


def test_vectorized_sampler_reads_same_field():
    c = _plan()
    m_female = dict(c["members"][0], actuarial_sex="female")
    f1 = _mc_vectorized_sample_death_ages(c, np.random.default_rng(7), 500, m_female, 0, 1960, 2026)
    f2 = _mc_vectorized_sample_death_ages(c, np.random.default_rng(7), 500, c["members"][1], 1, 1960, 2026)
    assert np.array_equal(f1, f2)
    m_default = _mc_vectorized_sample_death_ages(c, np.random.default_rng(7), 500, c["members"][0], 0, 1960, 2026)
    assert not np.array_equal(m_default, f1)
