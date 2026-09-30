"""End-user README staleness guard (finding DOC-204, system review
2026-09-07, Wave 6 item W6-5).

The shipped README (documentation/reference/readme/README.md) mentioned neither the
Monarch auto-update feature nor the Financial Trends Reporter companion app
at all -- both were documented only in maintainer-facing surfaces
(documentation/archive/superpowers/ and documentation/future/superpowers/), leaving the household running the packaged app with
no in-README pointer to either. A plain-language section was added in this
same change.

Mirrors tests/test_functional_spec_feature_currency_regression.py's fixed-
manifest pattern: when a new user-facing feature ships, document it in the
README and add its marker term here in the same change.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "documentation" / "reference" / "readme" / "README.md"

FEATURE_MARKERS = [
    ("Monarch auto-update", "Monarch auto-update"),
    ("Financial trends reporter", "Financial trends reporter companion app"),
]


def test_readme_mentions_every_known_shipped_optional_feature():
    text = README_PATH.read_text(encoding="utf-8")
    missing = [name for marker, name in FEATURE_MARKERS if marker not in text]
    assert missing == [], (
        f"documentation/reference/readme/README.md is missing a mention of: {missing}. "
        "Add a short plain-language section under '## Optional features' -- "
        "this guard exists because the README went stale on exactly this "
        "point once already (finding DOC-204, system review 2026-09-07)."
    )


def test_readme_does_not_claim_nothing_leaves_the_machine():
    """DOC-002: LIVE pricing sends ticker symbols to outside quote services."""
    text = README_PATH.read_text(encoding="utf-8")
    assert "nothing is sent anywhere over the internet" not in text
    assert "OFFLINE" in text and "ticker symbols" in text


def test_pricing_mode_card_discloses_outbound_calls():
    js = (ROOT / "frontend" / "js" / "dashboard_decomp_checklist_closeout.js").read_text(encoding="utf-8")
    assert "ticker symbols of your holdings" in js and "OFFLINE mode makes no outside calls" in js
