"""Unit tests for the RMD Joint Life table (finding F10 / Wave 2 item 2.9).

Covers: the IRS Table II lookup itself (core.joint_life_divisor), the
>10-year / sole-beneficiary gate in core.rmd_divisor and
planning_engines.rmd_divisor, the account-titling-based sole-beneficiary
detection with its age-gap fallback, and the explicit confirmation (required
by item 2.9's own verification note) that rmd_divisor's hardcoded age-72
floor cannot fire ahead of statutory_rmd_start_age's SECURE 2.0 73/75 ramp.
"""
from __future__ import annotations

import src.core as core
import src.planning_engines as pe


def test_joint_life_divisor_matches_irs_table_ii_values():
    # Hand-verified against IRS Publication 590-B (2025), Appendix B, Table II.
    assert core.joint_life_divisor(72, 50) == 36.9
    assert core.joint_life_divisor(75, 60) == 28.3
    assert core.joint_life_divisor(80, 65) == 23.8
    assert core.joint_life_divisor(90, 70) == 19.1


def test_joint_life_divisor_clamps_outside_tabulated_range():
    # Owner age above 105 clamps to the row-105 boundary.
    assert core.joint_life_divisor(120, 60) == core.joint_life_divisor(105, 60)
    # Spouse age below the table's minimum column (20) clamps to 20.
    assert core.joint_life_divisor(80, 5) == core.joint_life_divisor(80, 20)


def test_rmd_divisor_uses_joint_life_table_only_when_gap_exceeds_ten_and_sole_beneficiary():
    # Gap > 10, sole beneficiary spouse -> Joint Life divisor (larger than
    # Uniform Lifetime for the same owner age, since it reflects the younger
    # spouse's longer expected joint survival).
    joint = core.rmd_divisor(80, spouse_age=65, sole_beneficiary_spouse=True)
    uniform = core.rmd_divisor(80)
    assert joint == 23.8
    assert joint > uniform

    # Gap exactly 10 (not "more than 10") -> Uniform Lifetime, per the
    # statute's own "more than 10 years younger" threshold.
    assert core.rmd_divisor(80, spouse_age=70, sole_beneficiary_spouse=True) == uniform

    # sole_beneficiary_spouse=False -> Uniform Lifetime regardless of gap.
    assert core.rmd_divisor(80, spouse_age=50, sole_beneficiary_spouse=False) == uniform


def test_spouse_is_sole_beneficiary_defaults_true_with_no_titling_on_file():
    # Item 2.9's documented "age-gap fallback when titling is not explicit":
    # no account_titling record at all -> assume the spouse is the sole
    # beneficiary rather than silently withholding the Joint Life divisor.
    c = {"account_titling": {}}
    assert pe._spouse_is_sole_beneficiary(c, ["Member_1_IRA"], "Patricia") is True


def test_spouse_is_sole_beneficiary_false_when_titling_names_someone_else():
    c = {"account_titling": {
        "Member_1_IRA": {"primary_beneficiary": "Our Family Trust"},
    }}
    assert pe._spouse_is_sole_beneficiary(c, ["Member_1_IRA"], "Patricia") is False


def test_spouse_is_sole_beneficiary_true_when_titling_names_the_spouse():
    c = {"account_titling": {
        "Member_1_IRA": {"primary_beneficiary": "Patricia"},
    }}
    assert pe._spouse_is_sole_beneficiary(c, ["Member_1_IRA"], "Patricia") is True


def test_compute_rmds_applies_joint_life_table_for_a_much_younger_spouse():
    c = {
        "account_registry": [
            {"id": "Member_1_IRA", "owner_idx": 0, "tax": "pre_tax", "rmd": True},
        ],
        "rmd_start_age": 75,
        "account_titling": {},
        "h_name": "Matthew",
        "w_name": "Patricia",
    }
    bal = {"Member_1_IRA": 1_000_000.0}
    # h is 80, w is 65 -- a 15-year gap, sole beneficiary by fallback.
    result = pe.compute_rmds(c, bal, 2026, 80, 65, True, True)
    assert result["by_owner"][0]["divisor"] == 23.8
    assert result["h"] == 1_000_000.0 / 23.8


def test_compute_rmds_falls_back_to_uniform_lifetime_when_spouse_gap_is_ten_or_less():
    c = {
        "account_registry": [
            {"id": "Member_1_IRA", "owner_idx": 0, "tax": "pre_tax", "rmd": True},
        ],
        "rmd_start_age": 75,
        "account_titling": {},
        "h_name": "Matthew",
        "w_name": "Patricia",
    }
    bal = {"Member_1_IRA": 1_000_000.0}
    result = pe.compute_rmds(c, bal, 2026, 80, 72, True, True)  # 8-year gap
    assert result["by_owner"][0]["divisor"] == core.RMD_DIVISORS[80]


def test_compute_rmds_accepts_single_arg_divisor_fn_for_backward_compatibility():
    # A caller-supplied divisor_fn that only accepts one positional arg (the
    # pre-2.9 signature) must still work rather than raising TypeError.
    c = {
        "account_registry": [
            {"id": "Member_1_IRA", "owner_idx": 0, "tax": "pre_tax", "rmd": True},
        ],
        "rmd_start_age": 75,
    }
    bal = {"Member_1_IRA": 1_000_000.0}
    result = pe.compute_rmds(c, bal, 2026, 80, 65, True, True, divisor_fn=lambda age: 10.0)
    assert result["by_owner"][0]["divisor"] == 10.0


def test_age_72_floor_cannot_fire_ahead_of_statutory_rmd_start_age():
    """Item 2.9's own verification note: rmd_divisor's hardcoded age-72 floor
    must not fire before statutory_rmd_start_age's SECURE 2.0 73/75 ramp for
    a person born after 1950. compute_rmds is the only real call site and it
    gates on the per-owner start_age (sourced from statutory_rmd_start_age
    via data_io.py), not on rmd_divisor's internal age<72 check -- so a
    72-year-old born in 1960 (statutory start age 75) must draw $0 RMD."""
    c = {
        "account_registry": [
            {"id": "Member_1_IRA", "owner_idx": 0, "tax": "pre_tax", "rmd": True},
        ],
        # Born 1960 -> statutory_rmd_start_age == 75, not 72.
        "h_rmd_start_age": core.statutory_rmd_start_age(1960),
        "rmd_start_age": 75,
    }
    assert c["h_rmd_start_age"] == 75
    bal = {"Member_1_IRA": 1_000_000.0}
    result = pe.compute_rmds(c, bal, 2026, 72, 70, True, True)
    assert result["by_owner"][0]["divisor"] == 0.0
    assert result["h"] == 0.0
