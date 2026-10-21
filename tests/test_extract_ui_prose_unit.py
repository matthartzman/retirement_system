"""Unit test for tools/extract_ui_prose.py (Contextual Help Panel, Phase 0)."""
import csv
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "extract_ui_prose", Path(__file__).resolve().parent.parent / "tools" / "extract_ui_prose.py")
eup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eup)

JS = '''const STEPS = [
  { id: "demo", title: "Demo", desc: "Enter the household members and their birth dates.",
    intro: "Each person needs a legal name and a date of birth." },
];
const STEP_HELP = {
  demo: pageHelp("Demo", "Lists who is in the household and when each was born.", "Feeds every projection year.", "Pick a filing status.", "Changes taxes."),
};
STEP_HELP.actual_spending = STEP_HELP.demo;
function f(x) { return `<p class="section-note">This explains how the ${x} setting works for you.</p>` + '<div class="small">No data yet today.</div>' + '<div class="section-note warning">Warning: this overrides the budget.</div>'; }
'''


def test_extract_and_classify(tmp_path):
    (tmp_path / "frontend" / "js").mkdir(parents=True)
    (tmp_path / "frontend" / "js" / "dashboard.js").write_text(JS, encoding="utf-8")
    (tmp_path / "frontend" / "index.html").write_text(
        '<div class="small" title="Opens the help panel for this page">Hello there friend</div>', encoding="utf-8")
    out = tmp_path / "out.csv"
    rows = eup.run(tmp_path, out)
    assert out.exists()
    got = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [c for c in eup.COLUMNS if c not in got[0]] == []
    kinds = {r["source_kind"] for r in got}
    assert {"steps", "pagehelp", "class", "title"} <= kinds
    by_text = {r["text"]: r for r in got}
    assert by_text["No data yet today."]["class"] == "B"
    assert by_text["Warning: this overrides the budget."]["class"] == "C"
    assert any(r["step_id"] == "demo" and r["level"] == "page" for r in got)
    assert len(rows) == len(got)
