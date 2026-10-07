"""WP5.3: the plan interview's suggestion rules and the 'Turn on X?' self-suggest."""
from __future__ import annotations

import pytest

from src import module_catalog as mc
from src import plan_interview as pi
from src.server_services.plan_tier_service import entered_rows
from tests.plan_fixture import make_plan


def test_tier_answer_only_gives_the_preset_with_no_extras():
    out = pi.suggest({"detail": "standard"})
    assert out["tier"] == "standard" and out["extra_on"] == [] and out["reasons"] == []


def test_yes_answers_add_only_features_the_tier_lacks():
    out = pi.suggest({"detail": "simple", "heloc": True, "charity": True, "equity": False})
    assert out["extra_on"] == ["heloc", "daf_giving", "qcd_giving"]
    # Expert already has everything: nothing extra
    assert pi.suggest({"detail": "expert", "heloc": True, "business": True})["extra_on"] == []


@pytest.mark.parametrize("answers", [None, {}, {"detail": "huge"}, {"detail": "simple", "heloc": "yes"},
                                      {"detail": "simple", "nope": True}])
def test_bad_answers_raise(answers):
    with pytest.raises(ValueError):
        pi.suggest(answers)


def test_every_question_feature_is_a_switchable_feature():
    keys = set(mc.switchable_keys())
    for q in pi.QUESTIONS[1:]:
        assert set(q["features"]) <= keys, q["id"]
    assert [q["kind"] for q in pi.questions()][0] == "choice"


def test_apply_writes_tier_and_extras(tmp_path):
    ws = make_plan(tmp_path)
    with ws.store() as store:
        pi.apply_suggestion(store, pi.suggest({"detail": "simple", "heloc": True}))
        profile = mc.plan_profile(store)
        assert profile["tier"] == "simple" and profile["differing"] == ["heloc"]
        assert mc.stored_switch(store, "heloc") is True


def test_feature_suggestions_only_for_off_features_with_data(tmp_path):
    ws = make_plan(tmp_path)
    with ws.store() as store:
        mc.apply_tier(store, "simple")
        got = pi.feature_suggestions(store, lambda s, k: 3 if k == "estate_legacy_plan" else None)
        assert [g["key"] for g in got] == ["estate_legacy_plan"]
        assert got[0]["text"] == "Turn on Estate & Legacy? You have 3 rows entered for it."
        assert pi.feature_suggestions(store, entered_rows) is not None
