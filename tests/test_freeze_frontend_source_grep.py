"""Freeze-and-fix-forward for source-text assertions against the frontend.

System review 2026-08-04, quality finding `source-text-grep-implementation-pinning`
(rated high, effort XL). 141 of 228 test files read a source file and then
assert a string literal appears in the text -- 393 occurrences. The recommended
first step was explicitly the cheap one:

    "Option 2 now (cheap, stops growth) ... Add a lint/CI rule requiring new
     frontend-behavior tests to go through load_dashboard.mjs's vm-sandbox
     execution rather than dashboard.js string matching; leave the existing
     141 files as-is."

Why the pattern is a problem, in this codebase's own words: a substring check
passes even when the matched code path is dead or the string only appears in a
comment. tests/synthetic_plans.py had to add a tokenize-based comment-exclusion
guard precisely because plain substring search proved unreliable. It also fails
on refactors that preserve behaviour, and passes through refactors that change
behaviour while preserving strings -- which is exactly backwards.

This session hit both halves of that within an hour: improving two allocation
dropdown labels (a change the same review asked for) broke two tests with no
behavioural regression at all.

The mechanism mirrors tests/test_freeze_numbered_test_files.py, the pattern
this project already chose for this class of problem. Existing files are
grandfathered; a NEW file joining the pattern fails.

For new frontend coverage, in preference order:
  1. Drive the real UI (see tests/e2e/, Playwright) -- catches broken handlers
     and render-time exceptions that no string match can.
  2. Execute the function in the Node vm sandbox (tests/frontend/load_dashboard.mjs).
  3. Assert on server-rendered output or an API response.

Structural assertions -- "this file exists", "this module is under N lines" --
are legitimately text-based and are not what this freezes; they do not assert
behaviour.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
BASELINE_PATH = TESTS_DIR / "fixtures" / "frontend_source_grep_baseline.json"

# Reads a frontend asset...
_READS_FRONTEND = re.compile(
    r"""(frontend\s*/\s*["']js["']|["'][^"']*\.(?:js|html|css)["'])"""
)
# ...and asserts a string literal against the text it got back.
_ASSERTS_LITERAL = re.compile(
    r"""assert(?:In)?\s*\(?\s*['\"]|\bin\s+(?:js|html|css|text|src)\b"""
)


def _greps_frontend_source(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    if "read_text" not in source:
        return False
    return bool(_READS_FRONTEND.search(source) and _ASSERTS_LITERAL.search(source))


def _current_files() -> set[str]:
    return {p.name for p in TESTS_DIR.glob("test_*.py") if _greps_frontend_source(p)}


def _baseline_files() -> set[str]:
    return set(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def test_no_new_files_assert_on_frontend_source_text():
    new_files = sorted(_current_files() - _baseline_files())
    assert new_files == [], (
        "These test files newly assert string literals against frontend source "
        f"text: {new_files}.\n"
        "That pattern passes when the matched code is dead or the string is in a "
        "comment, breaks on behaviour-preserving refactors, and survives "
        "behaviour-changing ones. Prefer, in order: a Playwright journey "
        "(tests/e2e/), the Node vm sandbox (tests/frontend/load_dashboard.mjs), "
        "or an assertion on server/API output.\n"
        "If a structural check is genuinely the right tool, add the filename to "
        f"{BASELINE_PATH.relative_to(ROOT)} in the same change -- a reviewable "
        "opt-out, not a silent loosening."
    )


def test_baseline_has_no_stale_entries():
    """Removing the pattern from a file should retire its grandfathering.

    Otherwise the baseline only ever grows and the freeze slowly stops meaning
    anything.
    """
    stale = sorted(_baseline_files() - _current_files())
    assert stale == [], (
        f"{len(stale)} baseline entr(y/ies) no longer match the pattern: {stale[:10]}\n"
        "Either the file was deleted or its source-grep assertions were replaced "
        "(both good). Remove them from "
        f"{BASELINE_PATH.relative_to(ROOT)} so the freeze keeps shrinking."
    )


def test_baseline_is_smaller_than_the_whole_suite():
    """Sanity check on the detector itself.

    If a regex change made this match nearly every file, the freeze would be
    vacuous -- it would grandfather everything and never fire.
    """
    total = len(list(TESTS_DIR.glob("test_*.py")))
    frozen = len(_baseline_files())
    assert frozen < total * 0.75, (
        f"{frozen} of {total} test files are grandfathered. The detector is "
        "probably over-matching; tighten it rather than accepting a freeze that "
        "cannot fire."
    )
