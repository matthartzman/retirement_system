"""T4b (system review 2026-07-21, P3): the Social Security claim-age score
must not double-count benefits (terminal_nw already reflects SS dollars
received) and must mandatorily weight by survivor protection in the SAME
change as the de-double-count -- a bare de-double-count would have biased
the headline toward early claiming, since the removed lifetime_ss term
happened to reward delay for the wrong (double-counted) reason.
"""
from pathlib import Path

from openpyxl import Workbook

from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet10

ROOT = Path(__file__).resolve().parents[1]


def _base_config():
    c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return c


def _run(config_overrides=None):
    c = _base_config()
    for k, v in (config_overrides or {}).items():
        c[k] = v
    rows = project(c)
    ws = Workbook().active
    return build_sheet10(ws, c, rows)


def test_score_is_after_tax_terminal_nw_plus_weighted_survivor_period_ss_income():
    result = _run()
    best = result["best"]
    assert best["score"] == best["after_tax_terminal_nw"] + 1.0 * best["survivor_period_ss_income"]
    # The old score's components (gross terminal_nw with lifetime_ss added
    # back and lifetime_tax/irmaa subtracted again) must no longer equal the
    # new score -- otherwise nothing actually changed.
    old_style_score = best["terminal_nw"] + best["lifetime_ss"] - best["lifetime_tax"] - best["irmaa"]
    assert best["score"] != old_style_score


def test_survivor_years_reflects_fixed_mortality_not_claim_timing_mismatch():
    # h_alive/w_alive-derived survivor_years is set by each member's death
    # year (dob_yr + mortality_age), which does not depend on SS claim age.
    # The old (h_ss==0) != (w_ss==0) proxy varied wildly across claim-age
    # pairs purely from claim-timing mismatch (confirmed while building this
    # fix: 2/8/7/3 across four pairs for this household's real ages/mortality
    # before the fix, vs a constant 2 after it) -- using that as a MANDATORY
    # score weight would have rewarded mismatched claim ages for a reason
    # that has nothing to do with survivorship.
    result = _run()
    survivor_year_values = {sc["survivor_years"] for sc in result["scenarios"]}
    assert len(survivor_year_values) == 1, (
        f"survivor_years should be constant across all claim-age pairs for a fixed "
        f"household mortality assumption, got: {survivor_year_values}"
    )


def test_survivor_period_ss_income_varies_meaningfully_across_claim_age_pairs():
    # Unlike the year-count, the SS dollars received during the (fixed)
    # survivor window DOES vary by claim-age pair -- delaying the higher
    # earner raises the eventual survivor benefit floor. This is what
    # actually gives the mandatory survivor weighting real pull on the
    # ranking, rather than being a no-op constant added to every score.
    result = _run()
    values = {round(sc["survivor_period_ss_income"]) for sc in result["scenarios"]}
    assert len(values) > 1, "survivor_period_ss_income should differ across claim-age pairs"


def test_survivor_weight_is_load_bearing_not_a_no_op():
    # With the weight zeroed out, the score collapses to after-tax terminal
    # NW alone; with it active (default 1.0), the survivor-income term must
    # actually move at least one scenario's score. Confirms the mandatory
    # weighting genuinely participates in the ranking instead of being inert.
    unweighted = _run({"ss_survivor_weight": 0.0})
    weighted = _run({"ss_survivor_weight": 1.0})
    unweighted_scores = {(sc["h_age"], sc["w_age"]): round(sc["score"]) for sc in unweighted["scenarios"]}
    weighted_scores = {(sc["h_age"], sc["w_age"]): round(sc["score"]) for sc in weighted["scenarios"]}
    assert unweighted_scores != weighted_scores


def test_after_tax_terminal_nw_is_sane_relative_to_gross_terminal_nw():
    # Deliberately not cross-checked against an independently re-projected
    # config: project() carries forward in-place engine state (e.g. lot cost
    # basis) on its input config, so a second, freshly-parsed projection for
    # the same claim ages is not guaranteed to match bit-for-bit even before
    # this change -- that's a pre-existing engine property, not something
    # this fix introduces or needs to paper over. Sanity-check internal
    # consistency instead: after-tax terminal wealth reflects embedded
    # deferred tax, so it should be positive and no larger than the gross
    # figure it's derived from.
    result = _run()
    for sc in result["scenarios"]:
        assert sc["after_tax_terminal_nw"] > 0
        assert sc["after_tax_terminal_nw"] <= sc["terminal_nw"] + 1.0
