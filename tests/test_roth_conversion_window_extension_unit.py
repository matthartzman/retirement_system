"""Wave 3 item 3.2 (system review 2026-08-31, finding F3, Option 1): the
voluntary Roth conversion window used to hard-stop the year before RMDs
start (``conv_window_offset`` default -1), closing off the two highest-
value conversion opportunities -- the late pre-RMD gap years and the
survivor's compressed single-filer bracket years.

``conv_window_offset`` ships in every CSV plan with the schema-documented
default of -1 (see data_io.py) -- the row is always present, so presence in
the CSV can't distinguish "advisor left this at -1" from "advisor never
touched it". The value itself is therefore the signal this item uses:
-1 (the shipped default) now extends the window to plan end; any other
value is a deliberate override and stays authoritative, unchanged from
prior behavior except for the DOB-anchoring fix below.

A second, independent bug fixed alongside it: conversion_window_end_year()
anchored solely to the primary member's DOB/RMD age, with no reference to
a younger spouse's own (later) RMD start year, even when an explicit
offset override is in play.
"""
from src.planning_engines import conversion_window_end_year


def _base_config(**overrides):
    c = {
        "plan_start": 2026,
        "plan_end": 2056,
        "h_dob_yr": 1962,
        "w_dob_yr": 1962,
        "h_rmd_start_age": 75,
        "w_rmd_start_age": 75,
        "conv_window_offset": -1,
        "roth_max_conversion_years": 0,
    }
    c.update(overrides)
    return c


def test_default_offset_extends_the_window_to_plan_end():
    c = _base_config()
    assert conversion_window_end_year(c) == c["plan_end"]


def test_explicit_offset_keeps_the_legacy_rmd_relative_formula():
    c = _base_config(conv_window_offset=-1 - 5)  # advisor set -6, not the default -1
    # legacy_end = later RMD year + offset
    assert conversion_window_end_year(c) == (1962 + 75) - 6


def test_default_offset_reaches_the_survivors_single_filer_years():
    # A two-member household's survivor-filing-status years live well past
    # either spouse's RMD start age -- the whole point of extending to plan
    # end rather than a fixed RMD-relative offset.
    c = _base_config(h_dob_yr=1960, w_dob_yr=1962, h_rmd_start_age=75, w_rmd_start_age=75)
    survivor_years_start = 1960 + 75  # earlier of the two RMD-start years is well inside window
    end = conversion_window_end_year(c)
    assert end == c["plan_end"]
    assert end > survivor_years_start


def test_explicit_offset_anchors_to_whichever_member_reaches_rmd_age_later():
    # Regression guard for the primary-member-only anchoring bug: a younger
    # spouse reaching RMD age later than the primary member must extend an
    # EXPLICIT offset's window too, not just the (now-default) plan-end case.
    c = _base_config(h_dob_yr=1960, w_dob_yr=1966, h_rmd_start_age=75, w_rmd_start_age=75,
                      conv_window_offset=0)
    h_rmd_year = 1960 + 75
    w_rmd_year = 1966 + 75
    assert w_rmd_year > h_rmd_year, "fixture must actually exercise the later-spouse case"
    assert conversion_window_end_year(c) == w_rmd_year


def test_roth_max_conversion_years_cap_stays_authoritative_over_the_new_default():
    # The v8.3 governance cap must still bind even though the window's own
    # default is now much wider -- this is the exact mechanism that keeps
    # every shipped CSV plan's window unchanged today (max_conversion_years
    # ships at 10 in every template), since roth_max_conversion_years > 0
    # caps the window before the extended default is ever reached.
    c = _base_config(roth_max_conversion_years=10)
    assert conversion_window_end_year(c) == c["plan_start"] + 10 - 1
    assert conversion_window_end_year(c) < c["plan_end"]


def test_roth_max_conversion_years_cap_also_binds_an_explicit_offset():
    c = _base_config(conv_window_offset=10, roth_max_conversion_years=3)
    assert conversion_window_end_year(c) == c["plan_start"] + 3 - 1
