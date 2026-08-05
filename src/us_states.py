"""Canonical list of US states plus the District of Columbia.

Single source of truth for "state" pull-down inputs across Plan Data
(residence_state, Housing state, State Comparison target_state, etc.).
District of Columbia is not one of the 50 states, so it is appended as its
own explicit entry rather than folded silently into the state count.
"""
from __future__ import annotations

US_STATES: tuple[tuple[str, str], ...] = (
    ("Alabama", "AL"), ("Alaska", "AK"), ("Arizona", "AZ"), ("Arkansas", "AR"),
    ("California", "CA"), ("Colorado", "CO"), ("Connecticut", "CT"), ("Delaware", "DE"),
    ("Florida", "FL"), ("Georgia", "GA"), ("Hawaii", "HI"), ("Idaho", "ID"),
    ("Illinois", "IL"), ("Indiana", "IN"), ("Iowa", "IA"), ("Kansas", "KS"),
    ("Kentucky", "KY"), ("Louisiana", "LA"), ("Maine", "ME"), ("Maryland", "MD"),
    ("Massachusetts", "MA"), ("Michigan", "MI"), ("Minnesota", "MN"), ("Mississippi", "MS"),
    ("Missouri", "MO"), ("Montana", "MT"), ("Nebraska", "NE"), ("Nevada", "NV"),
    ("New Hampshire", "NH"), ("New Jersey", "NJ"), ("New Mexico", "NM"), ("New York", "NY"),
    ("North Carolina", "NC"), ("North Dakota", "ND"), ("Ohio", "OH"), ("Oklahoma", "OK"),
    ("Oregon", "OR"), ("Pennsylvania", "PA"), ("Rhode Island", "RI"), ("South Carolina", "SC"),
    ("South Dakota", "SD"), ("Tennessee", "TN"), ("Texas", "TX"), ("Utah", "UT"),
    ("Vermont", "VT"), ("Virginia", "VA"), ("Washington", "WA"), ("West Virginia", "WV"),
    ("Wisconsin", "WI"), ("Wyoming", "WY"),
)

DISTRICT_OF_COLUMBIA: tuple[str, str] = ("District of Columbia", "DC")


def states_and_dc() -> tuple[tuple[str, str], ...]:
    """The 50 states plus DC, DC listed separately as its own entry."""
    return US_STATES + (DISTRICT_OF_COLUMBIA,)


def state_name_choice_options() -> list[dict]:
    """Choice options where the stored value is the full state name."""
    return [{"value": name, "label": name} for name, _abbr in states_and_dc()]


def state_abbr_choice_options() -> list[dict]:
    """Choice options where the stored value is the 2-letter abbreviation."""
    return [{"value": abbr, "label": f"{name} ({abbr})"} for name, abbr in states_and_dc()]
