"""Plan interview (WP5.3, design 2026-10-04 P6): a short question flow that suggests a tier
and the switches to turn on beyond it, plus the "Turn on X?" suggestions for features that are
off while the plan holds data for them.

Pure rules over ``module_catalog``: no I/O. The question wording lives here and nowhere else
(the frontend renders what ``GET /api/plan/interview`` serves).
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import module_catalog as mc

TIER_QUESTION_ID = "detail"

# The first question picks the starting tier; each later yes/no question names the features
# a "yes" turns on beyond that tier. Wording is owner-reviewed (WP5.3 checkpoint).
QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": TIER_QUESTION_ID,
        "text": "How much detail do you want to manage in your plan?",
        "options": [
            {"value": "simple", "label": "Just the essentials: income, spending, savings, and whether the plan works"},
            {"value": "standard", "label": "The essentials plus common topics: estate, insurance, and Social Security timing"},
            {"value": "advanced", "label": "Detailed planning with tax and withdrawal strategy tools"},
            {"value": "expert", "label": "Everything, including specialist modules"},
        ],
    },
    {"id": "heloc", "text": "Do you have a home equity line of credit (HELOC), or might you use one?",
     "features": ["heloc"]},
    {"id": "charity", "text": "Do you give to charity through a donor-advised fund, or directly from an IRA (qualified charitable distributions)?",
     "features": ["daf_giving", "qcd_giving"]},
    {"id": "equity", "text": "Do you receive stock options, RSUs, or other equity compensation from an employer?",
     "features": ["equity_compensation"]},
    {"id": "business", "text": "Do you own a business, or expect to sell one?",
     "features": ["business_succession", "scorp_vs_llc"]},
    {"id": "care", "text": "Do you have long-term care or hybrid life/long-term care insurance, or want to plan for long-term care costs?",
     "features": ["hybrid_ltc_policy", "long_term_care_stress"]},
    {"id": "move", "text": "Are you considering moving, or downsizing your home?",
     "features": ["housing_location_search", "housing_trajectory_comparison"]},
    {"id": "state", "text": "Might you change your state of residence in retirement?",
     "features": ["state_residency"]},
]

_BY_ID = {q["id"]: q for q in QUESTIONS}


def questions() -> List[Dict[str, Any]]:
    """The questions as served: id, text, and for the tier question its options."""
    out = []
    for q in QUESTIONS:
        item = {"id": q["id"], "text": q["text"], "kind": "choice" if "options" in q else "yes_no"}
        if "options" in q:
            item["options"] = [dict(o) for o in q["options"]]
        out.append(item)
    return out


def suggest(answers: Dict[str, Any]) -> Dict[str, Any]:
    """The tier and extra switches the ``answers`` suggest.

    ``answers`` maps question id to a tier key (the tier question) or a bool (yes/no). The tier
    question is required. Returns ``{"tier", "extra_on": [...], "reasons": [{"key", "name",
    "question"}], "label"}``; ``extra_on`` holds only features the tier's preset does not
    already turn on, so a non-empty list makes the plan "customized". Raises ``ValueError``
    on a missing or unknown answer.
    """
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    unknown = sorted(set(answers) - set(_BY_ID))
    if unknown:
        raise ValueError(f"unknown question: {unknown[0]}")
    tier = answers.get(TIER_QUESTION_ID)
    if tier not in mc.TIERS:
        raise ValueError(f"{TIER_QUESTION_ID} must be one of: {', '.join(mc.TIERS)}")
    preset = mc.tier_preset(tier)
    extra: List[str] = []
    reasons: List[Dict[str, str]] = []
    for q in QUESTIONS[1:]:
        if q["id"] not in answers:
            continue
        ans = answers[q["id"]]
        if not isinstance(ans, bool):
            raise ValueError(f"{q['id']} must be true or false")
        if not ans:
            continue
        for key in q["features"]:
            if key not in preset and key not in extra:
                extra.append(key)
                reasons.append({"key": key, "name": mc.CATALOG[key].name, "question": q["id"]})
    order = {k: i for i, k in enumerate(mc.switchable_keys())}
    extra.sort(key=lambda k: order[k])
    reasons.sort(key=lambda r: order[r["key"]])
    return {"tier": tier, "label": mc.TIER_LABELS[tier], "extra_on": extra, "reasons": reasons}


def apply_suggestion(store: Any, suggestion: Dict[str, Any]) -> None:
    """Write a :func:`suggest` result to an open plan store: the tier preset, then the extras."""
    mc.apply_tier(store, suggestion["tier"])
    for key in suggestion["extra_on"]:
        mc.set_feature(store, key, True)


def feature_suggestions(store: Any, entered_rows) -> List[Dict[str, Any]]:
    """"Turn on X?" for every switchable feature that is off while the plan holds entered data
    for it. ``entered_rows(store, key)`` is ``plan_tier_service.entered_rows`` (None when the
    catalog declares no data location, which never suggests)."""
    out = []
    for key in mc.switchable_keys():
        if mc.stored_switch(store, key):
            continue
        n = entered_rows(store, key)
        if n:
            name = mc.CATALOG[key].name
            out.append({"key": key, "name": name, "entered_rows": n,
                        "text": f"Turn on {name}? You have {n} {'row' if n == 1 else 'rows'} entered for it."})
    return out
