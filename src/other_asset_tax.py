"""How a typed Other Asset (Assets & Protection > Other Asset Items) is taxed when sold.

One place for the treatment choices, the default for each asset type and the holding-period test, read by
the plan parser (``src/parsing/client_sections.py``) and, through the parsed ``other_asset_items``, by the
Current Snapshot. Design: documentation/future/superpowers/plans/
2026-11-06-alt-asset-gain-tax-and-change-breakdown-design-and-plan.md section 3.1.
"""
from __future__ import annotations

import re
from datetime import date

NONE, GAINS, COLLECTIBLE_GAINS = "none", "gains", "collectible_gains"

# Stored plan value (what the Other Asset Items table shows) -> treatment key. "" = the type's default.
TREATMENT_LABELS = {
    "Not taxed": NONE,
    "Taxed on gains": GAINS,
    "Taxed on gains (collectible)": COLLECTIBLE_GAINS,
}
LABEL_FOR = {v: k for k, v in TREATMENT_LABELS.items()}

# Federal cap on the long-term rate for collectibles (IRC 1(h)(4)).
COLLECTIBLE_LTCG_CAP = 0.28

_VEHICLE_TOKENS = ("auto", "boat", "vehicle", "car", "truck", "rv")

TREATMENT_NOTE = ("Not taxed | Taxed on gains | Taxed on gains (collectible). Blank = the type's default "
                  "(vehicles not taxed; art and collectibles collectible gains; everything else gains).")
_OTHER_ASSET_SUB = re.compile(r"^Other Asset\s+\d+$", re.I)


def added_field_rows(subsection: str) -> list[list[str]]:
    """The two plan rows (``[section, subsection, label, value, units, notes]``) added in 2026-11 for one Other
    Asset: written by the add endpoint for a new asset and backfilled into older assets."""
    return [
        ["Other Assets", subsection, "purchase_date", "", "date", "Date bought; held over one year is long-term."],
        ["Other Assets", subsection, "tax_treatment", "", "choice", TREATMENT_NOTE],
    ]


def backfill_rows(store) -> list[list[str]]:
    """``added_field_rows`` for every Other Asset in the plan (the backfill engine drops the keys it holds)."""
    subs: list[str] = []
    for r in store.rows("Other Assets"):
        sub = str(r["subsection"] or "")
        if _OTHER_ASSET_SUB.match(sub.strip()) and sub not in subs:
            subs.append(sub)
    return [row for sub in subs for row in added_field_rows(sub)]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")


def is_collectible_type(asset_type: str) -> bool:
    """Art and collectibles: the types net worth shows apart from start-up equity."""
    t = _norm(asset_type)
    return "art" in t.split("_") or "collectible" in t


def default_treatment(asset_type: str) -> str:
    """Vehicles are personal-use property (a gain is rare and a loss is never deductible): not taxed.
    Art and collectibles: collectible gains. Start-up equity and everything else: ordinary capital gains."""
    t = _norm(asset_type)
    if any(tok in t for tok in _VEHICLE_TOKENS):
        return NONE
    if is_collectible_type(asset_type):
        return COLLECTIBLE_GAINS
    return GAINS


def resolve_treatment(asset_type: str, stored: str) -> str:
    """The treatment key for a stored value (a label, or a key), falling back to the type's default."""
    text = str(stored or "").strip()
    if text in TREATMENT_LABELS:
        return TREATMENT_LABELS[text]
    folded = {k.casefold(): v for k, v in TREATMENT_LABELS.items()}
    if text.casefold() in folded:
        return folded[text.casefold()]
    if text in LABEL_FOR:
        return text
    return default_treatment(asset_type)


def parse_date(text: str) -> date | None:
    """An ISO ``YYYY-MM-DD`` (or ``M/D/YYYY``) date, else None."""
    t = str(text or "").strip()
    if not t:
        return None
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        pass
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def is_long_term(purchased: date | None, sold: date) -> bool:
    """Held more than one year (the day after the one-year anniversary or later). An unknown purchase date
    counts as long-term; callers say so to the user."""
    if purchased is None:
        return True
    try:
        anniversary = purchased.replace(year=purchased.year + 1)
    except ValueError:  # 29 Feb
        anniversary = date(purchased.year + 1, 3, 1)
    return sold > anniversary
