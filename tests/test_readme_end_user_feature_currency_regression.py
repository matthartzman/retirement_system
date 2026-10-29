"""End-user README staleness guard (finding DOC-204, system review
2026-09-07, Wave 6 item W6-5).

The shipped README (documentation/reference/readme/README.md) mentioned neither the
Monarch auto-update feature nor the Financial Insight companion app
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

from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "documentation" / "reference" / "readme" / "README.md"

FEATURE_MARKERS = [
    ("Third-party import auto-update", "Third-party import auto-update"),
    ("Financial Insight app", "Financial Insight companion app"),
    ("Concepts Guide", "Concepts Guide pointer"),
]

# DOC-003: menu names the README tells the reader to click must exist on screen.
SCREEN_NAMES = ["Data & Maintenance", "Plan Features", "Account Reconciliation", "Build & Results"]
CARD_TEXT = [
    ("dashboard_decomp_monarch_autoupdate.js", "Third-party import auto-update"),
    ("dashboard_decomp_monarch_autoupdate.js", "Enable daily auto-update"),
    ("dashboard_decomp_monarch_autoupdate.js", "Import now"),
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


def test_readme_screen_names_match_frontend_titles():
    text = README_PATH.read_text(encoding="utf-8")
    dash = dashboard_js_text()
    for name in SCREEN_NAMES:
        assert name in text, f"README should mention {name!r}"
        assert f'title: "{name}"' in dash, f"{name!r} is not a nav title in dashboard.js"
    for fname, label in CARD_TEXT:
        assert label in text, f"README should mention {label!r}"
        js = (ROOT / "frontend" / "js" / fname).read_text(encoding="utf-8")
        assert label in js, f"{label!r} is not on screen in {fname}"
    assert "Monarch auto-update" not in text


def test_readme_has_no_developer_commands():
    text = README_PATH.read_text(encoding="utf-8")
    assert "python -m pytest" not in text and "build_workbook" not in text
