"""Wave 3 item 3.4 (system review 2026-08-31, finding F1, Option 2): the
Priority-3 elective pre-tax withdrawal has always capped itself at a
bracket ceiling before falling through to taxable/trust -- but that
ceiling was hardcoded to the 24% federal bracket in
deterministic_engine.py, with no input to change it. This is the missing
input: withdrawal_bracket_target_rate makes the ceiling a real,
configurable policy ("fill ordinary income to the Nth bracket, then draw
taxable") without restructuring the fixed withdrawal cascade itself
(F1 Option 1, deferred).

Default 0.24 reproduces today's hardcoded rate exactly -- the frozen
golden master and synthetic library are unaffected by this item
(confirmed separately).

A note on scope for the "interaction with the Roth optimizer's bracket
cap" acceptance criterion: Priority 3 (this item's own mechanism) is the
ONLY tax-sensitive, bracket-capped elective pre-tax pass. Priority 4b (the
existing, pre-dating-this-item "final pre-tax draw before any Roth
withdrawal" pass, respect_tax_caps=False) deliberately draws MORE pre-tax
past any bracket ceiling once Priority 3 is exhausted, by design ("Roth is
a true last resort"). So the two mechanisms sharing a target rate correctly
interact at the Priority-3 level (tested directly here); a plan's total
elective withdrawal across the whole cascade is not expected to stay under
the bracket ceiling, and asserting that would test the wrong thing.
"""
from src.data_io import load_csv, parse_client
from src.planning_engines import project, withdraw_pretax_elective

from conftest import TEST_INPUT_DIR


def _scenario(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"  # isolate the withdrawal cascade from Roth conversion sizing
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    c.update(overrides)
    return c


def test_default_rate_matches_the_previously_hardcoded_24_percent_behavior():
    default_run = project(_scenario())
    explicit_24 = project(_scenario(withdrawal_bracket_target_rate=0.24))
    for r_default, r_explicit in zip(default_run, explicit_24):
        assert r_default.get("ira_wd", 0.0) == r_explicit.get("ira_wd", 0.0)
        assert r_default.get("total_tax", 0.0) == r_explicit.get("total_tax", 0.0)


def test_unmatched_rate_raises_instead_of_silently_capping_at_400k():
    rows_or_error = None
    try:
        project(_scenario(withdrawal_bracket_target_rate=0.23))
        rows_or_error = "no error"
    except ValueError as e:
        rows_or_error = str(e)
    assert rows_or_error != "no error", "an off-bracket rate must fail loud, not silently cap at $400,000"
    assert "matches no federal bracket rate" in rows_or_error


def test_a_real_rate_still_works_and_reaches_the_engine():
    c = _scenario(withdrawal_bracket_target_rate=0.32)
    rows = project(c)
    assert rows  # no exception


# ── withdraw_pretax_elective unit-level checks (Priority 3's own contract) ──
# These isolate the exact mechanism item 3.4 makes configurable, without the
# rest of the cascade's later, deliberately-uncapped priorities confounding
# the comparison.

def test_a_narrower_bracket_top_caps_the_draw_lower_than_a_wider_one():
    kwargs = dict(c={}, bal={"IRA": 1_000_000.0}, gap=200_000.0, agi=250_000.0,
                  taxable_inc=200_000.0, year=2030, filing="MFJ",
                  irmaa_threshold=1_000_000.0, marginal_rate=0.24)
    # Fake account registry / ids the real function reads off `c`.
    c = {"account_registry": [{"id": "IRA", "tax": "pre_tax", "owner_idx": 0}]}
    narrow = withdraw_pretax_elective(c, {"IRA": 1_000_000.0}, 200_000.0, 250_000.0, 200_000.0,
                                       2030, "MFJ", bracket_top_24=280_000.0, irmaa_threshold=1_000_000.0,
                                       marginal_rate=0.24)
    wide = withdraw_pretax_elective(c, {"IRA": 1_000_000.0}, 200_000.0, 250_000.0, 200_000.0,
                                     2030, "MFJ", bracket_top_24=500_000.0, irmaa_threshold=1_000_000.0,
                                     marginal_rate=0.24)
    assert narrow["amount"] == 30_000.0  # 280,000 - 250,000 headroom
    assert wide["amount"] == 250_000.0  # bracket headroom (500k - 250k = 250k) binds before the grossed-up gap
    assert narrow["amount"] < wide["amount"]


def test_agi_that_already_includes_a_roth_conversion_correctly_shrinks_headroom():
    # This is the actual "interaction with the Roth optimizer's bracket cap"
    # this item's acceptance criterion asks for: the SAME year's agi already
    # reflects whatever the Roth conversion consumed (deterministic_engine.py
    # builds agi from non_ss_income, which includes roth_conv, before Priority
    # 3 ever runs) -- so a larger conversion must leave correspondingly less
    # Priority-3 headroom under the SAME bracket_top_24, never double-filling.
    c = {"account_registry": [{"id": "IRA", "tax": "pre_tax", "owner_idx": 0}]}
    no_conversion = withdraw_pretax_elective(c, {"IRA": 1_000_000.0}, 300_000.0, agi=100_000.0,
                                              taxable_inc=80_000.0, year=2030, filing="MFJ",
                                              bracket_top_24=400_000.0, irmaa_threshold=1_000_000.0,
                                              marginal_rate=0.24)
    large_conversion = withdraw_pretax_elective(c, {"IRA": 1_000_000.0}, 300_000.0, agi=350_000.0,
                                                 taxable_inc=330_000.0, year=2030, filing="MFJ",
                                                 bracket_top_24=400_000.0, irmaa_threshold=1_000_000.0,
                                                 marginal_rate=0.24)
    assert no_conversion["amount"] == 300_000.0  # bracket headroom (300k) equals the gap
    assert large_conversion["amount"] == 50_000.0  # only 50k of bracket headroom left
    assert no_conversion["amount"] + 100_000.0 > large_conversion["amount"] + 350_000.0 - 300_000.0
    # Explicit shared-ceiling check: agi-at-call-time + amount never exceeds bracket_top_24
    # (mirrors production Priority-3's own respect_tax_caps=True contract).
    assert 100_000.0 + no_conversion["amount"] <= 400_000.0 + 1e-6
    assert 350_000.0 + large_conversion["amount"] <= 400_000.0 + 1e-6
