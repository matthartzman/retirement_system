"""Wave 3 item 3.8 (system review 2026-08-31, finding F11, Option 1
"restricted to the winner's neighbourhood"): the SS claim-age sweep scores
every pair against ONE fixed lifespan assumption -- longevity is the
dominant driver of claiming decisions, yet held fixed it cannot
differentiate the pairs at all. This re-scores only the top 3 ranked pairs
at a shorter and a longer lifespan, informationally, without changing the
primary recommendation.

A real bug was caught and fixed while building this: h_death_yr/w_death_yr
(data_io.py) are derived ONCE at parse time as h_dob_yr + h_mort_age and
never re-derived from h_mort_age afterward -- the engine reads the death
year, not the mortality-age input, so an earlier version of this feature
that only overrode h_mort_age/w_mort_age produced byte-identical
objective_value across every longevity variant (silently doing nothing).
test_longevity_variants_actually_change_the_score below guards against
that regression directly.
"""
import time
from pathlib import Path

from openpyxl import Workbook

from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet10

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR


def _run():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    rows = project(c)
    ws = Workbook().active
    return build_sheet10(ws, c, rows)


def test_scores_three_longevity_variants_for_the_top_three_pairs():
    result = _run()
    longevity_rows = result["longevity_rows"]
    assert len(longevity_rows) == 3  # shorter, configured, longer
    labels = [row[0] for row in longevity_rows]
    assert labels == ["Shorter lifespan", "Configured lifespan", "Longer lifespan"]
    for _label, _delta, pair_scores in longevity_rows:
        assert len(pair_scores) == 3  # top 3 ranked pairs, re-scored under this variant


def test_longevity_variants_actually_change_the_score():
    # Regression guard for the h_death_yr staleness bug this item's own
    # commit message documents: h_mort_age alone has zero effect on the
    # engine, so a naive override would report identical scores across
    # every variant. A longer lifespan must score strictly higher than a
    # shorter one for the same claim-age pair (more years of income/
    # consumption captured), never equal.
    result = _run()
    longevity_rows = result["longevity_rows"]
    shorter = dict(((h, w), obj) for h, w, obj, _is_best in longevity_rows[0][2])
    longer = dict(((h, w), obj) for h, w, obj, _is_best in longevity_rows[2][2])
    assert shorter.keys() == longer.keys()
    for pair in shorter:
        assert longer[pair] > shorter[pair], (
            f"pair {pair}: longer-lifespan score ({longer[pair]}) should exceed "
            f"shorter-lifespan score ({shorter[pair]}), not match or fall below it"
        )


def test_configured_variant_matches_the_scenarios_already_computed():
    # The "Configured lifespan" row must reuse the main sweep's own
    # already-computed objective_value for each top pair (no re-run), both
    # for correctness (it's the same household, same claim ages, same
    # lifespan -- must be identical) and for cost (item 3.8 exists to be
    # cheap; re-running the base case again would defeat that).
    result = _run()
    top_pairs = result["scenarios"][:3]
    configured_row = next(row for row in result["longevity_rows"] if row[0] == "Configured lifespan")
    configured_scores = {(h, w): obj for h, w, obj, _is_best in configured_row[2]}
    for pair in top_pairs:
        assert configured_scores[(pair["h_age"], pair["w_age"])] == pair["objective_value"]


def test_flags_whether_the_recommendation_is_stable_across_longevity():
    result = _run()
    assert isinstance(result["longevity_pair_is_stable"], bool)


def test_stays_within_a_reasonable_build_time_budget():
    # This item's own acceptance criterion (system review Wave 3 table):
    # "build time within budget". A prior implementation that let the
    # longevity variants fall through to the sweep's Monte Carlo /
    # survivor-bucket-rebuild path took several minutes for ONE sheet on
    # this household -- this asserts the fixed (deterministic-only,
    # skip_mc=True) version stays fast.
    start = time.monotonic()
    _run()
    elapsed = time.monotonic() - start
    assert elapsed < 60, f"build_sheet10 took {elapsed:.1f}s -- longevity refinement must stay cheap"
