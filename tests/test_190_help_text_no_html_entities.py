"""Help and nav text must not be pre-escaped in source.

`esc()` in dashboard.js escapes `&` to `&amp;` at render time, and every STEPS
`help`/`title` value and every `pageHelp()` argument passes through it. A source
literal that already contains an HTML entity therefore double-escapes, and the
user sees the literal text `&amp;` in the help panel.

Raw HTML template strings are a different case: there `&amp;` is correct, because
the text is injected as markup rather than escaped. This module only inspects the
escaped-at-render authoring surfaces.

Review finding D1 (medium/S), Option 2: fix the literals and keep them fixed.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"

# Entities that would survive esc() and render visibly to the user.
ENTITY = re.compile(r"&(amp|lt|gt|quot|#39|nbsp);")

# Authoring surfaces that are escaped at render time:
#   help: "..."   /  title: "..."   -- STEPS and STEP_HELP entries
ESCAPED_FIELD = re.compile(r'^\s*(help|title):\s*"((?:[^"\\]|\\.)*)"')


def _offenders():
    found = []
    for lineno, line in enumerate(DASHBOARD_JS.read_text(encoding="utf-8").splitlines(), 1):
        match = ESCAPED_FIELD.match(line)
        if match and ENTITY.search(match.group(2)):
            found.append((lineno, match.group(1), match.group(2)[:80]))
    return found


def test_step_help_and_title_literals_carry_no_html_entities():
    offenders = _offenders()
    assert not offenders, (
        "These STEPS help/title literals are pre-escaped and will render the raw "
        "entity to the user; write the bare character instead:\n"
        + "\n".join(f"  dashboard.js:{n} ({field}) {text}" for n, field, text in offenders)
    )


def test_detector_catches_a_planted_entity():
    """Guard against the check silently passing because the regex stopped matching."""
    planted = '    help: "Entered on Insurance &amp; LTC Policies.",'
    match = ESCAPED_FIELD.match(planted)
    assert match is not None, "ESCAPED_FIELD no longer matches the help: literal form"
    assert ENTITY.search(match.group(2)), "ENTITY no longer detects &amp;"
