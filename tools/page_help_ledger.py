#!/usr/bin/env python3
"""Fact ledger for the merged page help records (Contextual Help Panel, Phase 2a).

Reads the page-level sources (STEPS desc/intro/help and the STEP_HELP pageHelp arguments in
frontend/js/dashboard.js, plus the WI-033 summary and glossary in frontend/js/help_registry.js),
reads the drafts file documentation/future/page_help_drafts.json, and checks that every number,
percent, age, proper noun and glossary term found in a page's sources still appears in its merged
record. A fact that does not is reported as a flag; flags are never resolved silently.

Usage:
  python tools/page_help_ledger.py check  [--drafts PATH] [--strict]
  python tools/page_help_ledger.py review [--drafts PATH] [--out PATH]
  python tools/page_help_ledger.py slots  [--drafts PATH] [--csv PATH]

check   prints ledger problems and lost facts per page; exit 1 with --strict when any exist.
review  writes the review document (sources beside merged record, ledger flags, batch order).
slots   fills the `slot` column of ui_prose_inventory.csv for every page-level row (or marks it D).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_ui_prose as eup  # noqa: E402

DASHBOARD = ROOT / "frontend" / "js" / "dashboard.js"
REGISTRY = ROOT / "frontend" / "js" / "help_registry.js"
DRAFTS = ROOT / "documentation" / "future" / "page_help_drafts.json"
REVIEW = ROOT / "documentation" / "future" / "page_help_review.md"

SLOTS = ["whatFor", "connections", "options", "impact"]
RECORD_FIELDS = ["summary"] + SLOTS
CODES = {"STEPS.desc": "d", "STEPS.intro": "i", "STEPS.help": "h", "pageHelp.meaning": "m",
         "pageHelp.connections": "c", "pageHelp.options": "o", "pageHelp.impact": "x"}
CODE_NAMES = {"s": "WI-033 summary", "d": "STEPS.desc", "i": "STEPS.intro", "h": "STEPS.help",
              "m": "pageHelp meaning", "c": "pageHelp connections", "o": "pageHelp options",
              "x": "pageHelp impact"}
# STEP_HELP keys that are not one of the 28 STEPS pages: legacy sub-pages now reached from, or
# redirected into, these pages (STEP_HELP.actual_spending is itself an alias of ytd_transactions).
SUB_PAGE = {
    "spending_mortgage_events": "spending_core", "spending_travel_extras": "spending_core",
    "spending_travel": "spending_core", "spending_setup": "spending_core",
    "spending_dashboard": "actual_spending", "ytd_transactions": "actual_spending",
    "assumption_signoff": "reports_and_review", "review": "reports_and_review",
    "build_impact": "reports_and_review", "plan_data_report": "reports_and_review",
    "planning_workbench": "strategy_workbench", "planning_levers": "strategy_optimize",
    "state_residency": "strategy_optimize", "allocation_policy": "strategy_optimize",
    "allocation_assets": "strategy_optimize", "withdrawal_strategy": "strategy_optimize",
    "scenarios": "strategy_scenarios", "monte_carlo_options": "strategy_stress",
    "divorce_options": "strategy_stress", "survivor_stress": "strategy_stress",
    "ltc_stress": "strategy_stress",
}

_ABBREV = ("e.g.", "i.e.", "vs.", "etc.", "approx.")
_SPELLED = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
            "eight": "8", "nine": "9", "ten": "10", "twelve": "12", "thirty": "30"}
_SENT_START = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?(?:%|½)?")
_CAP = re.compile(r"[A-Z][\w]*(?:-[\w]+)*")
_WORD = re.compile(r"[A-Za-z][\w'-]*")


def split_sentences(text: str) -> list[str]:
    parts, cur = [], ""
    for chunk in _SENT_START.split(text.strip()):
        cur = f"{cur} {chunk}".strip() if cur else chunk
        if cur.lower().endswith(_ABBREV):
            continue
        parts.append(cur)
        cur = ""
    if cur:
        parts.append(cur)
    return parts


# ------------------------------------------------------------------ source loading
def _parse_registry(root: Path):
    src = (root / "frontend" / "js" / "help_registry.js").read_text(encoding="utf-8")
    glossary = {}
    block = src.split("export const GLOSSARY = {", 1)[1].split("\n};", 1)[0]
    for m in re.finditer(r'^\s*"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*)",?\s*$', block, re.M):
        glossary[json.loads(f'"{m.group(1)}"')] = json.loads(f'"{m.group(2)}"')
    pages = {}
    pblock = src.split("export const HELP_PAGES = {", 1)[1].split("\n};", 1)[0]
    for m in re.finditer(r'^  "(\w+)":\s*\{', pblock, re.M):
        body = pblock[m.end():]
        end = re.search(r'^  \}|\}(?:,)?\s*$', body, re.M)
        body = body[:end.start()] if end else body
        s = re.search(r'"summary":\s*"((?:[^"\\]|\\.)*)"', body)
        t = re.search(r'"terms":\s*\[(.*?)\]', body, re.S)
        pages[m.group(1)] = {
            "summary": json.loads(f'"{s.group(1)}"') if s else "",
            "terms": json.loads(f"[{t.group(1)}]") if t else [],
        }
    pre = re.search(r"PRE_BUILD_PAGES\s*=\s*\[(.*?)\]", src, re.S)
    pre_build = re.findall(r'"(\w+)"', pre.group(1)) if pre else []
    return glossary, pages, pre_build


def load_sources(root: Path = ROOT):
    """Return (pages, glossary, pre_build): pages[id] = {title, summary, terms, sources[]}.

    Each source is {id, code, text, key, line} with one sentence per entry; ids are
    `<code><n>` (`<key>.<code><n>` when the sentence comes from a legacy sub-page help key).
    """
    glossary, reg_pages, pre_build = _parse_registry(root)
    path = root / "frontend" / "js" / "dashboard.js"
    rows = eup.scan_js(path, "frontend/js/dashboard.js")
    src_text = path.read_text(encoding="utf-8")
    step_ids = re.findall(r'^    id: "(\w+)"', src_text.split("const STEP_HELP", 1)[0], re.M)
    titles = dict(re.findall(r'^    id: "(\w+)",\s*\n\s*group: "[^"]*",\s*\n\s*title: "([^"]*)"',
                             src_text, re.M))
    pages = {}
    for pid in step_ids:
        reg = reg_pages.get(pid, {})
        pages[pid] = {"title": titles.get(pid, pid), "summary": reg.get("summary", ""),
                      "terms": reg.get("terms", []), "sources": []}
        if reg.get("summary"):
            pages[pid]["sources"].append({"id": "s1", "code": "s", "text": reg["summary"],
                                          "key": pid, "line": 0})
    counters = {}
    for r in rows:
        if r["level"] != "page" or r["sub"] not in CODES:
            continue
        key = r["step_id"]
        pid = key if key in pages else SUB_PAGE.get(key)
        if pid is None:
            continue
        code = CODES[r["sub"]]
        prefix = "" if key == pid else f"{key}."
        for sent in split_sentences(r["text"]):
            n = counters[(pid, prefix, code)] = counters.get((pid, prefix, code), 0) + 1
            pages[pid]["sources"].append({"id": f"{prefix}{code}{n}", "code": code, "text": sent,
                                          "key": key, "line": int(r["line"])})
    return pages, glossary, pre_build


# ------------------------------------------------------------------ fact extraction
def _norm(tok: str) -> str:
    t = tok.lower().strip("-'")
    t = _SPELLED.get(t, t)
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def _glossary_alts(term: str) -> list[str]:
    alts = [re.sub(r"\s*\(.*?\)", "", term).strip()]
    alts += re.findall(r"\(([^)]*)\)", term)
    return [a.lower() for a in alts if a]


def _term_re(alt: str):
    words = [re.escape(w) + r"(?:s|es)?" for w in alt.split()]
    return re.compile(r"(?<![\w])" + r"\s+".join(words) + r"(?![\w])", re.I)


def proper_nouns(sentences: list[str], global_set: set) -> set:
    out = set()
    for s in sentences:
        toks = list(_WORD.finditer(s))
        for i, m in enumerate(toks):
            w = m.group(0)
            if not w[0].isupper() or w == "I":
                continue
            initial = i == 0
            acronym = len(w) > 1 and w.isupper()
            if initial and not acronym and _norm(w) not in global_set:
                continue
            out.add(_norm(w))
    return out


def _mid_sentence_caps(all_sentences: list[str]) -> set:
    """Words capitalised mid-sentence somewhere and never written lower case (so not plain words)."""
    caps, lower = set(), set()
    for s in all_sentences:
        for i, m in enumerate(_WORD.finditer(s)):
            w = m.group(0)
            if w[0].isupper():
                if i:
                    caps.add(_norm(w))
            else:
                lower.add(_norm(w))
    return caps - lower


def acronyms(text: str) -> set:
    """All-caps words (SSA, CASH, RMD): case matters, so 'cash' does not stand in for 'CASH'."""
    return {_norm(w.group(0)).upper() for w in _WORD.finditer(text)
            if len(w.group(0)) > 1 and w.group(0).isupper()}


def numbers(text: str) -> set:
    found = {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text)}
    for w in _WORD.finditer(text):
        if w.group(0).lower() in _SPELLED:
            found.add(_SPELLED[w.group(0).lower()])
    return found


def record_text(record: dict) -> str:
    return " ".join(str(record.get(f, "")) for f in RECORD_FIELDS)


def lost_facts(sources: list[dict], record: dict, glossary: dict, global_caps: set) -> list[dict]:
    """Facts present in any source sentence but absent from the merged record."""
    rec = record_text(record)
    rec_nums = numbers(rec)
    rec_caps = proper_nouns(split_sentences(rec), global_caps)
    rec_caps |= {_norm(w.group(0)) for w in _WORD.finditer(rec)}  # any-case presence counts
    rec_acr = acronyms(rec)
    terms = {t: [_term_re(a) for a in _glossary_alts(t)] for t in glossary}
    flags, seen = [], set()
    for src in sources:
        text = src["text"]
        for n in sorted(numbers(text)):
            if n not in rec_nums and ("number", n) not in seen:
                seen.add(("number", n))
                flags.append({"kind": "number", "fact": n, "source": src["id"]})
        for a in sorted(acronyms(text) - rec_acr):
            if ("proper noun", a.lower()) not in seen:
                seen.add(("proper noun", a.lower()))
                flags.append({"kind": "proper noun", "fact": a, "source": src["id"]})
        for p in sorted(proper_nouns([text], global_caps)):
            if p not in rec_caps and ("proper noun", p) not in seen:
                seen.add(("proper noun", p))
                flags.append({"kind": "proper noun", "fact": p, "source": src["id"]})
        for term, res in terms.items():
            if any(r.search(text) for r in res) and ("glossary term", term) not in seen:
                if not any(r.search(rec) for r in res):
                    seen.add(("glossary term", term))
                    flags.append({"kind": "glossary term", "fact": term, "source": src["id"]})
    return flags


# ------------------------------------------------------------------ ledger checks
FATES = ("kept", "merged", "dropped")


def draft_problems(page: dict) -> list[str]:
    """Problems found in the draft alone (no sources needed): empty slots, bad fates, kept text missing."""
    led = {e["id"]: e for e in page.get("ledger", [])}
    probs = []
    for f in RECORD_FIELDS:
        if not str(page.get("record", {}).get(f, "")).strip():
            probs.append(f"record.{f} is empty")
    for e in page.get("ledger", []):
        fate = e.get("fate")
        if fate not in FATES:
            probs.append(f"{e['id']}: fate '{fate}' is not one of {FATES}")
        elif fate == "dropped":
            of = e.get("of") or []
            if not of or any(led.get(o, {}).get("fate") not in ("kept", "merged") for o in of):
                probs.append(f"{e['id']}: dropped entry must name kept/merged sentences it repeats")
        else:
            if e.get("slot") not in RECORD_FIELDS:
                probs.append(f"{e['id']}: fate {fate} needs a slot from {RECORD_FIELDS}")
            elif fate == "kept" and e.get("text") not in str(page["record"].get(e["slot"], "")):
                probs.append(f"{e['id']}: marked kept but its text is not in record.{e['slot']}")
    return probs


def ledger_problems(page: dict, sources: list[dict]) -> list[str]:
    """Structural problems: source sentences with no fate, stale text, bad drop references."""
    led = {e["id"]: e for e in page.get("ledger", [])}
    probs = []
    for s in sources:
        e = led.get(s["id"])
        if e is None:
            probs.append(f"{s['id']}: source sentence has no ledger entry")
        elif e.get("text") != s["text"]:
            probs.append(f"{s['id']}: source text changed since the draft was written")
    src_ids = {s["id"] for s in sources}
    for e in page.get("ledger", []):
        if e["id"] not in src_ids:
            probs.append(f"{e['id']}: ledger entry has no matching source sentence")
    return probs + draft_problems(page)


def check(drafts: dict, pages: dict, glossary: dict) -> dict:
    """Return {page_id: {"problems": [...], "lost": [...]}} for every page in `pages`."""
    all_sent = [s["text"] for p in pages.values() for s in p["sources"]]
    global_caps = _mid_sentence_caps(all_sent)
    out = {}
    for pid, page in pages.items():
        d = drafts.get("pages", {}).get(pid)
        if d is None:
            out[pid] = {"problems": ["no draft record for this page"], "lost": []}
            continue
        out[pid] = {"problems": ledger_problems(d, page["sources"]),
                    "lost": lost_facts(page["sources"], d["record"], glossary, global_caps)}
    return out


# ------------------------------------------------------------------ review document
def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def review_order(pages: dict, pre_build: list) -> list:
    """The pre-build pages first, then the rest in nav order in batches of 4 or 5."""
    pre = [p for p in pre_build if p in pages]
    rest = [p for p in pages if p not in pre]
    batches = [("Pre-build pages (11)", pre)]
    sizes, i = [], 0
    n = len(rest)
    k = max(1, round(n / 4.5))
    base, extra = divmod(n, k)
    sizes = [base + (1 if j < extra else 0) for j in range(k)]
    for j, size in enumerate(sizes, 1):
        batches.append((f"Batch {j}", rest[i:i + size]))
        i += size
    return batches


def render_review(drafts: dict, pages: dict, glossary: dict, pre_build: list) -> str:
    results = check(drafts, pages, glossary)
    n_flags = sum(len(r["lost"]) + len(r["problems"]) for r in results.values())
    n_notes = sum(len(d.get("notes", [])) for d in drafts["pages"].values())
    lines = [
        "Status: draft for review (Phase 2a, generated by `python tools/page_help_ledger.py review`; "
        f"{len(pages)} pages, {n_flags} lost-fact or ledger flags, {n_notes} reviewer notes shown under each page; "
        "nothing applied to the app yet).",
        "",
        "# Page help drafts: review",
        "",
        "Plan: `Contextual Help Panel Design and Implementation plan.md`, Phase 2. Drafts live in "
        "`page_help_drafts.json`; edit the record text there (or tell me the change) and re-run "
        "`python tools/page_help_ledger.py check`.",
        "",
        "## How to read this",
        "",
        "- Each page shows its sources beside the merged record, slot by slot. Source tags: "
        "`s` WI-033 summary, `d` STEPS.desc, `i` STEPS.intro, `h` STEPS.help, `m` pageHelp meaning, "
        "`c` connections, `o` options, `x` impact. A prefix such as `ytd_transactions.` marks a "
        "legacy sub-page help key folded into this page.",
        "- Fate marks: **kept** = sentence reused as written; **merged** = its facts are folded into a "
        "reworded sentence; **dropped** = pure repetition of the named sentence(s).",
        "- Flags are facts (number, percent, age, proper noun, glossary term) that appear in a source "
        "but not in the merged record, plus ledger problems. Flags are listed, not resolved: decide each "
        "one (restore the fact, or accept the loss).",
        "- Page-level sentences with different facts are merged by synthesis; `dropped` is used only for "
        "repetition (plan section 3.1).",
        "- The 11 pre-build pages are `PRE_BUILD_PAGES` in `help_registry.js` (Household & People to "
        "Estate & Legacy), not the WI-033 Part A list.",
        "",
    ]
    for title, ids in review_order(pages, pre_build):
        lines += [f"## {title}", ""]
        for pid in ids:
            lines += _render_page(pid, pages[pid], drafts["pages"].get(pid), results[pid])
    return "\n".join(lines).rstrip() + "\n"


def _render_page(pid: str, page: dict, draft: dict | None, res: dict) -> list:
    out = [f"### {page['title']} (`{pid}`)", ""]
    if draft is None:
        return out + ["No draft record.", ""]
    led = {e["id"]: e for e in draft["ledger"]}
    by_slot = {f: [] for f in RECORD_FIELDS}
    dropped = []
    for s in page["sources"]:
        e = led.get(s["id"], {})
        fate = e.get("fate", "unassigned")
        tag = f"`{s['id']}` **{fate}**" + (f" (of {', '.join(e['of'])})" if e.get("of") else "")
        item = f"{tag}: {s['text']}"
        if fate == "dropped" or fate == "unassigned":
            dropped.append(item)
        else:
            by_slot[e.get("slot", "whatFor")].append(item)
    out += ["| Slot | Sources | Merged record |", "|---|---|---|"]
    for f in RECORD_FIELDS:
        out.append(f"| {f} | {_cell('<br>'.join(by_slot[f]))} | {_cell(str(draft['record'].get(f, '')))} |")
    if dropped:
        out.append(f"| dropped / unassigned | {_cell('<br>'.join(dropped))} | |")
    out.append(f"| terms | | {_cell(', '.join(draft['record'].get('terms', [])))} |")
    out.append("")
    flags = [f"- lost {f['kind']} `{f['fact']}` (from `{f['source']}`)" for f in res["lost"]]
    flags += [f"- ledger: {p}" for p in res["problems"]]
    flags += [f"- note: {n}" for n in draft.get("notes", [])]
    out += ["**Flags**", ""] + (flags or ["- none"]) + [""]
    return out


# ------------------------------------------------------------------ inventory slot column
def slot_for_rows(rows: list[dict], pages: dict, drafts: dict) -> list[str]:
    """Slot per inventory row: HELP_PAGES[id].slot, 'D' when every sentence was dropped, '' off-page."""
    by_line = {}
    for pid, page in pages.items():
        for s in page["sources"]:
            by_line.setdefault((s["line"], s["key"]), []).append((pid, s["id"]))
    out = []
    for r in rows:
        if r.get("level") != "page" or r.get("source_kind") not in ("steps", "pagehelp"):
            out.append("")
            continue
        hits = by_line.get((int(r["line"]), r["step_id"]), [])
        slots = []
        for pid, sid in hits:
            e = {x["id"]: x for x in drafts["pages"][pid]["ledger"]}.get(sid, {})
            if e.get("fate") in ("kept", "merged"):
                slots.append(f"HELP_PAGES[{pid}].{e['slot']}")
        out.append(";".join(dict.fromkeys(slots)) if slots else ("D" if hits else "UNMAPPED"))
    return out


def fill_slot_column(csv_path: Path, pages: dict, drafts: dict) -> int:
    """Add or refresh the `slot` column of the inventory CSV; returns the number of UNMAPPED page rows."""
    import csv
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames)
        rows = list(reader)
    for r, slot in zip(rows, slot_for_rows(rows, pages, drafts)):
        r["slot"] = slot
    if "slot" not in fields:
        fields.append("slot")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return sum(1 for r in rows if r["slot"] == "UNMAPPED")


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "review", "slots"])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--drafts", type=Path, default=DRAFTS)
    ap.add_argument("--out", type=Path, default=REVIEW)
    ap.add_argument("--csv", type=Path, default=ROOT / "documentation" / "future" / "ui_prose_inventory.csv")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any flag or problem exists")
    a = ap.parse_args(argv)
    pages, glossary, pre_build = load_sources(a.root)
    drafts = json.loads(a.drafts.read_text(encoding="utf-8"))
    if a.command == "review":
        a.out.write_text(render_review(drafts, pages, glossary, pre_build), encoding="utf-8")
        print(f"wrote {a.out}")
        return 0
    if a.command == "slots":
        missing = fill_slot_column(a.csv, pages, drafts)
        print(f"slot column written to {a.csv}; {missing} page rows unmapped")
        return 1 if missing else 0
    results = check(drafts, pages, glossary)
    total = 0
    for pid, r in results.items():
        for p in r["problems"]:
            print(f"{pid}: PROBLEM {p}")
        for f in r["lost"]:
            print(f"{pid}: LOST {f['kind']} '{f['fact']}' (from {f['source']})")
        total += len(r["problems"]) + len(r["lost"])
    print(f"{len(results)} pages checked, {total} flags")
    return 1 if (a.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
