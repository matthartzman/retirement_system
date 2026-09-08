"""Finding ARC-7 (system review 2026-09-07, Wave 6 item W6-4): the demo and
frozen-fixture client_policy.csv files' mc_engine_mode notes column
described exact-scalar as "the default" while the row's own value was
quick_vectorized -- self-contradictory, and stale relative to the live
app's actual post-1.1-flip default (advanced_exact_scalar, input/client_policy.csv).
This pins the corrected, non-contradictory note text; it does not change
either file's mc_engine_mode *value*.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mc_engine_mode_row(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Model Constants,Monte Carlo,mc_engine_mode,"):
            return line
    raise AssertionError(f"no mc_engine_mode row found in {path}")


def test_frozen_fixture_note_no_longer_calls_quick_vectorized_the_default():
    row = _mc_engine_mode_row(ROOT / "tests" / "fixtures" / "sample_plan_frozen" / "client_policy.csv")
    assert row.split(",", 3)[3].startswith("quick_vectorized"), "this test must not change the pinned value"
    assert "Advisor-ready default exact scalar path" not in row
    assert "advanced_exact_scalar" not in row.lower() or "Advanced Exact Scalar" in row


def test_demo_client_policy_note_no_longer_calls_quick_vectorized_the_default():
    path = ROOT / "input" / "demo" / "client_policy.csv"
    if not path.exists():
        return  # not every checkout ships the demo fixture
    row = _mc_engine_mode_row(path)
    assert row.split(",", 3)[3].startswith("quick_vectorized"), "this test must not change the pinned value"
    assert "Advisor-ready default exact scalar path" not in row
