#!/usr/bin/env python3
"""Extract user-visible explanatory prose from the frontend (Contextual Help Panel, Phase 0).

Scans frontend/js/*.js and frontend/index.html for prose carried by prose-style CSS
classes, title= tooltips, STEPS desc/intro/help and pageHelp(...) arguments, then writes
documentation/future/ui_prose_inventory.csv with a class guess (A/B/C/D), level, step id,
destination and duplicate-merge columns (plan section 3.1).

Usage: python tools/extract_ui_prose.py [--out PATH] [--root PATH]
The class column is a heuristic guess for human review, not a final decision.
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "documentation" / "future" / "ui_prose_inventory.csv"
COLUMNS = ["file", "line", "class", "text", "level", "step_id", "destination",
           "merged_into", "unique_info_kept", "source_kind"]

PROSE_CLASS = re.compile(
    r"(^|-)(small|note|muted|hint|banner|warn|warning|empty|question|desc|info|sub|meta|help)($|-)")
SKIP_CLASS = {"btn", "badge", "help-title", "help-body"}
TAG_RE = re.compile(r"<(\w+)\b([^>]*?)>([^<]*)", re.S)
CLASS_RE = re.compile(r"""class=\\?["']([^"']*)""")
TITLE_RE = re.compile(r"""\btitle=\\?["']([^"'<>]*)""")
REGEX_PREV = set("(,=:[!&|?{};") | {"return", "typeof", ""}

# Module -> step ids it renders into (best guess; "" when shared). Reviewed by hand.
MODULE_STEPS = {
    "dashboard_decomp_allocation_optimizer.js": "strategy_optimize",
    "dashboard_decomp_housing_optimizer.js": "strategy_housing",
    "dashboard_decomp_housing_scenarios.js": "strategy_housing",
    "dashboard_decomp_rental_properties.js": "assets_special",
    "dashboard_decomp_holdings.js": "holdings",
    "dashboard_decomp_spending_taxonomy.js": "spending_core",
    "dashboard_decomp_spending_sources.js": "spending_core",
    "dashboard_decomp_spending_adjustments.js": "spending_core",
    "dashboard_decomp_large_discretionary.js": "spending_core",
    "dashboard_decomp_income_streams.js": "income_retirement",
    "dashboard_decomp_assets_other.js": "assets_special",
    "dashboard_decomp_death_benefits.js": "annuity_death_benefits",
    "dashboard_decomp_estate_insurance.js": "estate",
    "dashboard_decomp_tax_assumptions.js": "taxes",
    "dashboard_decomp_roth_guardrails.js": "roth_conversion",
    "dashboard_decomp_conversion.js": "roth_conversion",
    "dashboard_decomp_monarch_reconciliation.js": "ytd_transactions",
    "dashboard_decomp_monarch_autoupdate.js": "ytd_transactions",
    "dashboard_decomp_ytd_and_plan_folder_io.js": "ytd_transactions",
    "dashboard_decomp_checklist_closeout.js": "start",
    "dashboard_decomp_home_panels.js": "start",
    "dashboard_decomp_plan_switcher.js": "start",
    "dashboard_decomp_plan_tiers.js": "start",
    "dashboard_decomp_plan_features.js": "start",
    "dashboard_decomp_build_history.js": "start",
    "dashboard_decomp_build_lifecycle.js": "start",
    "dashboard_decomp_local_backups.js": "settings",
    "dashboard_decomp_state_inputs.js": "household_people",
    "dashboard_decomp_mc_stress_options.js": "strategy_stress",
    "dashboard_decomp_optimizer_apply.js": "strategy_optimize",
    "dashboard_decomp_strategy_workspace.js": "strategy",
    "dashboard_decomp_page_recommendations.js": "",
    "dashboard_decomp_field_choice_help.js": "",
    "dashboard_decomp_row_model.js": "",
    "dashboard_decomp_misc.js": "",
    "spending_dashboard.js": "actual_spending",
    "reports_ui.js": "reports",
    "planning_workbench_ui.js": "strategy_planning_cases",
    "admin.js": "settings",
    "help_registry.js": "(glossary)",
    "index.html": "(shell)",
}


# ---------------------------------------------------------------- JS tokenizer
class Lit:
    __slots__ = ("text", "line", "prev", "prev2", "call", "argi", "kind")

    def __init__(self, text, line, prev, prev2, call, argi, kind):
        self.text, self.line, self.prev, self.prev2 = text, line, prev, prev2
        self.call, self.argi, self.kind = call, argi, kind


def tokenize_literals(src: str):
    """Yield Lit for each string / template literal outside comments and regexes."""
    i, n, line = 0, len(src), 1
    prev, prev2 = "", ""
    parens = []  # (is_pagehelp, argcount, key)
    out = []
    last_ident = ""

    def skip_expr(j, ln):
        """Skip a ${...} expression starting after '${'; return (index, line, placeholder)."""
        depth = 1
        while j < n and depth:
            c = src[j]
            if c == "\n":
                ln += 1
            if c in "'\"":
                j, ln = skip_simple(j, ln)
                continue
            if c == "`":
                j, ln, _ = read_template(j, ln)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        return j, ln

    def skip_simple(j, ln):
        q = src[j]
        j += 1
        while j < n and src[j] != q:
            if src[j] == "\\":
                j += 1
            if j < n and src[j] == "\n":
                ln += 1
            j += 1
        return j + 1, ln

    def read_template(j, ln):
        j += 1
        buf = []
        while j < n and src[j] != "`":
            c = src[j]
            if c == "\\" and j + 1 < n:
                buf.append(src[j + 1] if src[j + 1] != "n" else " ")
                j += 2
                continue
            if c == "$" and src[j + 1:j + 2] == "{":
                j, ln = skip_expr(j + 2, ln)
                buf.append("\x00")
                continue
            if c == "\n":
                ln += 1
            buf.append(c)
            j += 1
        return j + 1, ln, "".join(buf)

    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            line += src.count("\n", i, end)
            i = end
        elif c in "'\"":
            start_line, q = line, c
            j, buf = i + 1, []
            while j < n and src[j] != q and src[j] != "\n":
                if src[j] == "\\" and j + 1 < n:
                    nxt = src[j + 1]
                    if nxt == "\n":
                        line += 1
                    buf.append(" " if nxt == "n" else nxt)
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            i = j + 1
            call = parens[-1] if parens else None
            out.append(Lit("".join(buf), start_line, prev, prev2,
                           call[2] if call and call[0] else None,
                           call[1] if call and call[0] else None, "str"))
            prev2, prev = prev, '"str"'
        elif c == "`":
            start_line = line
            j, ln, text = read_template(i, line)
            line, i = ln, j
            call = parens[-1] if parens else None
            out.append(Lit(text, start_line, prev, prev2,
                           call[2] if call and call[0] else None,
                           call[1] if call and call[0] else None, "tpl"))
            prev2, prev = prev, '"str"'
        elif c == "/" and prev in REGEX_PREV:
            j, in_cls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_cls = True
                elif src[j] == "]":
                    in_cls = False
                elif src[j] == "/" and not in_cls:
                    break
                j += 1
            i = j + 1
            prev2, prev = prev, "/re/"
        elif c.isalpha() or c in "_$":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word = src[i:j]
            i = j
            prev2, prev = prev, word
            last_ident = word
        elif c.isdigit():
            while i < n and (src[i].isalnum() or src[i] == "."):
                i += 1
            prev2, prev = prev, "0"
        else:
            if c == "(":
                is_ph = prev == "pageHelp"
                key = ""
                if is_ph:
                    # key is the token before ':' preceding pageHelp
                    key = _key_before(src, i)
                parens.append((is_ph, 0, key))
            elif c == ")" and parens:
                parens.pop()
            elif c == "," and parens and parens[-1][0]:
                p = parens.pop()
                parens.append((p[0], p[1] + 1, p[2]))
            i += 1
            prev2, prev = prev, c
    return out


def _key_before(src: str, paren_idx: int) -> str:
    m = re.search(r"""([A-Za-z_$][\w$]*|['"][\w$]+['"])\s*:\s*pageHelp\s*$""", src[max(0, paren_idx - 80):paren_idx])
    return m.group(1).strip("'\"") if m else ""


# ---------------------------------------------------------------- text helpers
def clean(text: str) -> str:
    t = text.replace("\x00", "{…}")
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def is_prose(t: str) -> bool:
    words = re.findall(r"[A-Za-z]{2,}", t.replace("{…}", " "))
    return len(words) >= 3


def is_prose_class(classes: str) -> bool:
    toks = classes.split()
    if any(t in SKIP_CLASS for t in toks):
        return False
    return any(PROSE_CLASS.search(t) for t in toks if "\x00" not in t and "$" not in t)


def level_for(classes: str) -> str:
    c = classes
    if "section-note" in c or "subsection" in c or "rc-sub" in c:
        return "section"
    if "field" in c or "setting-help" in c:
        return "field"
    return "message"


WARN_RE = re.compile(
    r"\b(warn|warning|error|fail|failed|cannot|can't|must|invalid|required|overrid|"
    r"permanent|irreversible|delete|will replace|overwrit|lost|danger|caution|do not|don't|"
    r"mismatch|exceed|blocked|not saved|unsaved)\w*", re.I)
STATE_RE = re.compile(
    r"^(no |not |none|loading|empty|stale|n/a|nothing|waiting|select |choose )|"
    r"\b(yet|loaded|available|saved|ready|complete[d]?|pending|stale)\W*$|\bsaved\b|\bbuilt\b", re.I)


def guess_class(text: str, classes: str, source_kind: str) -> str:
    t = text.replace("{…}", "").strip()
    if source_kind in ("steps", "pagehelp"):
        return "A"
    if "warn" in classes or "danger" in classes:
        return "C"
    if WARN_RE.search(t) and len(t) < 220:
        return "C"
    if "empty" in classes or STATE_RE.search(t):
        if len(t) < 120:
            return "B"
    if len(t.replace("{…}", "")) < 28 and "{…}" in text:
        return "B"
    return "A"


def norm_tokens(t: str) -> set:
    stop = set("the a an of to and or in on for is are be this that it with as at by from you your can will may if when "
               "each per any all which what how use used using see here".split())
    return {w for w in re.findall(r"[a-z0-9%$]+", t.lower()) if w not in stop and len(w) > 2}


# ---------------------------------------------------------------- scanning
def html_items(text: str):
    """Yield (classes_or_attr, prose_text, kind) found in an HTML-ish fragment."""
    for m in TAG_RE.finditer(text):
        attrs, body = m.group(2), clean(m.group(3))
        cm = CLASS_RE.search(attrs)
        if cm and is_prose_class(cm.group(1)) and is_prose(body):
            yield cm.group(1), body, "class"
        tm = TITLE_RE.search(attrs)
        if tm:
            tt = clean(tm.group(1))
            if is_prose(tt) and len(tt.split()) >= 3:
                yield "title", tt, "title"


def scan_js(path: Path, rel: str):
    src = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    cur_step = ""
    in_steps = rel.endswith("dashboard.js")
    steps_end = src.find("const STEP_HELP") if in_steps else -1
    pos_steps_end_line = src.count("\n", 0, steps_end) + 1 if steps_end > 0 else 0
    sh_end = src.find("STEP_HELP.actual_spending =") if in_steps else -1  # end of STEP_HELP map
    sh_end_line = src.count("\n", 0, sh_end) + 1 if sh_end > 0 else 0
    default_step = MODULE_STEPS.get(Path(rel).name, "")
    pending = None  # (classes) of an open prose tag at the end of the previous literal
    for lit in tokenize_literals(src):
        text = lit.text
        if pending is not None:
            if lit.prev == "+":
                body = clean(text.split("<", 1)[0])
                if is_prose(body):
                    rows.append(dict(file=rel, line=lit.line, text=body, level=level_for(pending),
                                     step_id=default_step, source_kind="class", sub=pending))
            pending = None
        m_open = re.search(r"""<\w+\b[^>]*class=\\?["']([^"']*)\\?["'][^>]*>\s*$""", text)
        if m_open and is_prose_class(m_open.group(1)):
            pending = m_open.group(1)
        if rel.endswith("dashboard.js") and lit.line < pos_steps_end_line:
            if lit.prev == ":" and lit.prev2 == "id":
                cur_step = text
            elif lit.prev == ":" and lit.prev2 in ("desc", "intro", "help"):
                t = clean(text)
                if is_prose(t):
                    rows.append(dict(file=rel, line=lit.line, text=t, level="page", step_id=cur_step,
                                     source_kind="steps", sub=f"STEPS.{lit.prev2}"))
                continue
            elif lit.prev == ":" and lit.prev2 == "label":
                continue
        if lit.call is not None and lit.argi is not None:
            t = clean(text)
            if is_prose(t) and lit.argi >= 1:  # argi 0 is the page title, not prose
                names = ["title", "meaning", "connections", "options", "impact"]
                a = names[lit.argi] if lit.argi < len(names) else f"arg{lit.argi}"
                rows.append(dict(file=rel, line=lit.line, text=t, level="field" if (sh_end_line and lit.line > sh_end_line) or lit.argi == 0 else "page",
                                 step_id=lit.call or "", source_kind="pagehelp", sub=f"pageHelp.{a}"))
            continue
        if "<" in text or "title=" in text:
            for classes, body, kind in html_items(text):
                lvl = "field" if kind == "title" else level_for(classes)
                rows.append(dict(file=rel, line=lit.line, text=body, level=lvl,
                                 step_id=default_step, source_kind=kind, sub=classes))
    return rows


def scan_html(path: Path, rel: str):
    rows = []
    for ln, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for classes, body, kind in html_items(line):
            rows.append(dict(file=rel, line=ln, text=body, level="field" if kind == "title" else level_for(classes),
                             step_id="(shell)", source_kind=kind, sub=classes))
    return rows


# ---------------------------------------------------------------- dedupe / destination
def assign(rows):
    for r in rows:
        r["class"] = guess_class(r["text"], r["sub"], r["source_kind"])
        r.update(destination="", merged_into="", unique_info_kept="")
    # Duplicate grouping: within the same step id (or exact text anywhere), token-set overlap.
    keep = [r for r in rows if r["class"] == "A"]
    order = {"pagehelp": 0, "steps": 1}
    keep.sort(key=lambda r: (-len(norm_tokens(r["text"])), order.get(r["source_kind"], 2)))
    survivors = []
    for r in keep:
        tk = norm_tokens(r["text"])
        if not tk:
            continue
        hit = None
        for s in survivors:
            same_scope = s["step_id"] == r["step_id"] or s["text"] == r["text"]
            if not same_scope:
                continue
            inter = len(tk & s["_tk"])
            if inter / len(tk) >= 0.8 and len(tk) <= len(s["_tk"]):
                hit = s
                break
        if hit is None:
            r["_tk"] = tk
            survivors.append(r)
        else:
            extra = sorted(tk - hit["_tk"])
            r["class"] = "D"
            r["merged_into"] = f"{hit['file']}:{hit['line']}"
            r["unique_info_kept"] = ("none" if not extra else "fold: " + " ".join(extra))
    for r in rows:
        r["destination"] = destination(r)
    return rows


def destination(r):
    c, lvl = r["class"], r["level"]
    if c == "D":
        return "delete"
    if c in ("B", "C"):
        return "stay (one line, data-kind=%s)" % ("state" if c == "B" else "warn")
    if lvl == "page":
        return f"HELP_PAGES[{r['step_id'] or '?'}]"
    if lvl == "section":
        return f"HELP_SECTIONS (page {r['step_id'] or '?'})"
    if lvl == "field":
        return "HELP_FIELDS (field help)"
    return f"HELP_SECTIONS (page {r['step_id'] or '?'})"


def coupled_tests(rows, root: Path):
    """Return {test file: [row index,...]} for tests that quote a long fragment of inventory text."""
    frags = {}
    for i, r in enumerate(rows):
        seg = max(r["text"].split("{…}"), key=len).strip()
        if len(seg) >= 30:
            frags[i] = re.sub(r"\s+", " ", seg[:60])
    hits = {}
    for p in sorted((root / "tests").rglob("*")):
        if p.suffix not in (".py", ".mjs", ".js") or not p.is_file():
            continue
        body = re.sub(r"\s+", " ", p.read_text(encoding="utf-8", errors="replace"))
        found = [i for i, f in frags.items() if f in body]
        if found:
            hits[str(p.relative_to(root))] = found
    return hits


def run(root: Path, out: Path):
    rows = []
    for p in sorted((root / "frontend" / "js").glob("*.js")):
        rows += scan_js(p, f"frontend/js/{p.name}")
    idx = root / "frontend" / "index.html"
    if idx.exists():
        rows += scan_html(idx, "frontend/index.html")
    assign(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--coupled-tests", action="store_true",
                    help="also list tests that quote inventory text")
    a = ap.parse_args(argv)
    rows = run(a.root, a.out)
    print(f"wrote {len(rows)} rows to {a.out}")
    if a.coupled_tests:
        for f, idx in coupled_tests(rows, a.root).items():
            print(f"{f}\t{len(idx)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
