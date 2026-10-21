"""Unit test for tools/page_help_ledger.py (Contextual Help Panel, Phase 2a)."""
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("page_help_ledger", ROOT / "tools" / "page_help_ledger.py")
phl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(phl)

DASH = '''const STEPS = [
  {
    id: "demo",
    group: "Household",
    title: "Demo Page",
    desc: "Enter the household members and their birth dates.",
    intro: "Delaying past full retirement age adds about 8% per year up to age 70. Social Security starts later.",
    help: "Filing status sets the tax brackets.",
  },
];
const STEP_HELP = {
  demo: pageHelp("Demo Page", "Lists who is in the household.", "Feeds every projection year of Medicare.", "Pick a filing status.", "Changes your lifetime taxes."),
};
STEP_HELP.actual_spending = STEP_HELP.demo;
'''
REGISTRY = '''export const GLOSSARY = {
  "Filing status": "The category you use on your tax return.",
  "Tax bracket": "A range of income taxed at one rate."
};
export const HELP_PAGES = {
  "demo": {"summary": "Who is in the household and how they file.", "terms": ["Filing status"]}
};
export const PRE_BUILD_PAGES = ["demo"];
'''


def _root(tmp_path):
    (tmp_path / "frontend" / "js").mkdir(parents=True)
    (tmp_path / "frontend" / "js" / "dashboard.js").write_text(DASH, encoding="utf-8")
    (tmp_path / "frontend" / "js" / "help_registry.js").write_text(REGISTRY, encoding="utf-8")
    return tmp_path


def _draft(pages, **record):
    """Draft whose ledger marks every source sentence kept in the given slot (test shortcut)."""
    rec = {"summary": pages["demo"]["summary"], "whatFor": "w", "connections": "c", "options": "o",
           "impact": "i", "terms": ["Filing status"]}
    rec.update(record)
    ledger = [{"id": s["id"], "source": "x", "text": s["text"], "fate": "kept", "slot": "whatFor"}
              for s in pages["demo"]["sources"]]
    return {"pages": {"demo": {"title": "Demo Page", "record": rec, "ledger": ledger}}}


def test_split_sentences_keeps_abbreviations():
    got = phl.split_sentences("Use e.g. a ticker. Then save it. Done?")
    assert got == ["Use e.g. a ticker.", "Then save it.", "Done?"]


def test_load_sources_ids_and_summary(tmp_path):
    pages, glossary, pre = phl.load_sources(_root(tmp_path))
    assert pre == ["demo"] and "Filing status" in glossary
    ids = [s["id"] for s in pages["demo"]["sources"]]
    assert ids == ["s1", "d1", "i1", "i2", "h1", "m1", "c1", "o1", "x1"]
    assert pages["demo"]["title"] == "Demo Page"


def test_lost_numbers_proper_nouns_and_terms_are_flagged(tmp_path):
    pages, glossary, _ = phl.load_sources(_root(tmp_path))
    full = " ".join(s["text"] for s in pages["demo"]["sources"])
    ok = _draft(pages, whatFor=full)
    assert phl.check(ok, pages, glossary)["demo"] == {"problems": [], "lost": []}

    lossy = _draft(pages, whatFor="Delaying adds a bonus. Social starts later. Lists who is in the household.")
    lost = {(f["kind"], f["fact"]) for f in phl.check(lossy, pages, glossary)["demo"]["lost"]}
    assert ("number", "8%") in lost and ("number", "70") in lost
    assert ("proper noun", "medicare") in lost
    assert ("glossary term", "Filing status") in lost


def test_missing_and_stale_ledger_entries_are_problems(tmp_path):
    pages, glossary, _ = phl.load_sources(_root(tmp_path))
    full = " ".join(s["text"] for s in pages["demo"]["sources"])
    d = _draft(pages, whatFor=full)
    d["pages"]["demo"]["ledger"].pop(1)
    d["pages"]["demo"]["ledger"][2]["text"] = "changed"
    probs = " | ".join(phl.check(d, pages, glossary)["demo"]["problems"])
    assert "no ledger entry" in probs and "source text changed" in probs


def test_dropped_must_name_kept_sentence():
    page = {"record": {f: "x" for f in phl.RECORD_FIELDS},
            "ledger": [{"id": "a", "text": "x", "fate": "dropped", "of": ["b"]},
                       {"id": "b", "text": "y", "fate": "dropped", "of": ["a"]}]}
    assert len(phl.draft_problems(page)) == 2


def test_acronym_case_matters(tmp_path):
    pages, glossary, _ = phl.load_sources(_root(tmp_path))
    assert phl.acronyms("Use CASH at 1.00") == {"CASH"}
    assert "CASH" not in phl.acronyms("Use cash at 1.00")


def test_slot_column_and_review(tmp_path):
    root = _root(tmp_path)
    pages, glossary, pre = phl.load_sources(root)
    full = " ".join(s["text"] for s in pages["demo"]["sources"])
    d = _draft(pages, whatFor=full)
    d["pages"]["demo"]["ledger"][1].update(fate="dropped", slot=None, of=["s1"])
    d["pages"]["demo"]["ledger"][0].update(fate="kept", slot="summary")
    inv = tmp_path / "inv.csv"
    with inv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "line", "text", "level", "step_id", "source_kind"])
        w.writeheader()
        src = {s["id"]: s for s in pages["demo"]["sources"]}
        for sid in ("d1", "i1", "m1"):
            w.writerow(dict(file="frontend/js/dashboard.js", line=src[sid]["line"], text=src[sid]["text"],
                            level="page", step_id="demo", source_kind="steps" if sid != "m1" else "pagehelp"))
        w.writerow(dict(file="x.js", line=1, text="note", level="message", step_id="demo", source_kind="class"))
    assert phl.fill_slot_column(inv, pages, d) == 0
    rows = list(csv.DictReader(inv.open(encoding="utf-8")))
    assert [r["slot"] for r in rows] == ["D", "HELP_PAGES[demo].whatFor", "HELP_PAGES[demo].whatFor", ""]
    text = phl.render_review(d, pages, glossary, pre)
    assert text.startswith("Status:") and "Demo Page (`demo`)" in text


def test_committed_drafts_are_self_consistent():
    drafts = json.loads((ROOT / "documentation" / "future" / "page_help_drafts.json").read_text(encoding="utf-8"))
    assert len(drafts["pages"]) == 28
    for pid, page in drafts["pages"].items():
        assert phl.draft_problems(page) == [], pid
        assert all(e["fate"] != "unassigned" for e in page["ledger"]), pid


def test_committed_inventory_has_slot_for_every_page_row():
    rows = list(csv.DictReader((ROOT / "documentation" / "future" / "ui_prose_inventory.csv").open(encoding="utf-8")))
    drafts = json.loads((ROOT / "documentation" / "future" / "page_help_drafts.json").read_text(encoding="utf-8"))
    page_rows = [r for r in rows if r["level"] == "page" and r["source_kind"] in ("steps", "pagehelp")]
    assert len(page_rows) >= 250
    for r in page_rows:
        assert r["slot"] == "D" or r["slot"].startswith("HELP_PAGES["), r
        for part in filter(None, r["slot"].split(";")):
            if part != "D":
                pid = part[len("HELP_PAGES["):part.index("]")]
                assert pid in drafts["pages"]
