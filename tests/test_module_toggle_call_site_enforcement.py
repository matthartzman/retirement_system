"""Every optional-module toggle read in ``src/`` is backed by a declaration.

#330 §3.4's enforcement half (master plan W5). The new ``degrades_without``
field is only worth having if it stays true, and a declaration that nothing
checks drifts exactly the way ``section``/``letter_prefix`` drifted — which is
the failure #329 exists to kill. So: sweep ``src/`` for toggle reads, and
assert every one of them outside the named module's own gate is backed by a
catalog declaration.

**What counts as a toggle read.** The plan names two spellings —
``module_enabled(`` and a raw ``c['opt']`` read — and this sweep looks for
exactly those, not for a semantic notion of "places that consult a toggle":

* a call to anything whose name ends in ``module_enabled`` (this deliberately
  catches ``spending_tracker._existing_life_insurance_module_enabled``, which
  re-reads ``client_optional_functions.csv`` by hand rather than going through
  the accessor — a toggle read is a toggle read regardless of the door it uses);
* a read of the ``'opt'`` key off any mapping, whether spelled ``c['opt']`` or
  ``c.get('opt')``. The spec describes ``deterministic_engine.py`` as reading
  ``c['opt']`` "directly"; in the source that is spelled ``.get``, so both
  spellings are in scope or the sweep would miss the site the spec is about.

Writes are not reads: ``data_io.py``'s ``c['opt'] = {...}`` is the loader that
*populates* the toggles, and it is filtered out by subscript context rather
than by an exemption, so it cannot silently start reading one day.

**Why AST rather than a line grep.** A regex over lines matches the word
``module_enabled`` inside the prose comment that explains it, and ``c['opt']``
inside four docstrings — six phantom sites in ``module_catalog.py`` alone, none
of which is code. Anchoring on the parse tree also yields the enclosing
function name for free, which is what lets a site be identified stably (see
below) instead of by a line number that any edit above it invalidates.

**Why the sweep still runs, given the plan says to write the findings in as a
fixture.** :data:`DECLARED_SITES` *is* that fixture: the judgement — which
module consumes each site, and under which of the three verdicts — was made
once, by hand, and is recorded here rather than re-derived. What runs per-test
is only the cheap mechanical half (an ``ast.parse`` of ~90 files, well under a
second), and it is what makes the fixture enforcing rather than decorative: a
frozen list cannot notice the eleventh call site, and noticing it is the entire
point.

A site is identified by ``(file, enclosing function, toggle)``, never by line
number, so moving code within a file does not churn this fixture.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import module_catalog as mc  # noqa: E402

SRC = ROOT / "src"

# The toggle read is a dynamic key (a loop variable), not a literal.
DYNAMIC = "<dynamic>"
# The site reads the whole ``opt`` mapping; which keys it then pulls out is
# recorded by the fixture, not derivable from this node.
RAW_OPT = "<c['opt']>"

# ── The three verdicts ───────────────────────────────────────────────────────
#
# OWN_GATE   The site *is* the gate for the module it names: the code that
#            decides whether that module's own work runs at all. Nothing to
#            declare -- a module does not depend on itself.
# SOFT       A different module's output is shaped by this toggle. Must be
#            backed by `degrades_without` (or `requires_outputs`, if the
#            consumer genuinely cannot build without it) on the consumer.
# ENGINE     The projection/tax layer, which is not a module and has no
#            builder. Must be backed by `engine_participation` on the module
#            named. This is #330 §3.4's item 4; W7 changes how these sites read
#            the toggle, not that they read it.
# ACCESSOR   module_catalog's own implementation of the gate.
OWN_GATE, SOFT, ENGINE, ACCESSOR = "own_gate", "soft", "engine", "accessor"


# ── The fixture: every toggle read in src/, classified ───────────────────────
#
# Swept 2026-09-21 (W5). Ten sites. Keyed by (file, function, toggle); the
# value is (verdict, consumer, keys_read, why). `consumer` is the catalog key
# whose output the site shapes -- None where there isn't one. `keys_read` is
# the module keys the site reads when the sweep cannot see them itself (a
# dynamic key, or a raw `opt` mapping read); empty otherwise.
DECLARED_SITES: dict[tuple[str, str, str], tuple[str, str | None, tuple[str, ...], str]] = {
    # ── The accessor itself ──────────────────────────────────────────────────
    ("src/module_catalog.py", "_base_enabled", RAW_OPT): (
        ACCESSOR, None, (),
        "The gate's own implementation: env overrides layered over saved c['opt'].",
    ),
    ("src/module_catalog.py", "module_status", DYNAMIC): (
        ACCESSOR, None, (),
        "Reports every optional module's gate state to the settings UI.",
    ),

    # ── Gates: the site decides whether its own module runs ──────────────────
    ("src/reporting/workbook_builder.py", "main", "market_luck_stress_test"): (
        OWN_GATE, None, (),
        "run_mc -- the 'no logic executed' half of gating Monte Carlo itself.",
    ),
    ("src/reporting/workbook_builder.py", "main", DYNAMIC): (
        OWN_GATE, None, (),
        "The generic loop over OPTIONAL_MODULE_SHEETS: each module's own gate, "
        "which is why the key is a loop variable and not a literal.",
    ),
    ("src/reporting/workbook_builder.py", "apply_final_workbook_structure",
     "scorp_vs_llc"): (
        OWN_GATE, None, (),
        "W8a: the S-Corp vs LLC sheet is extracted from Sheet 9 by copying "
        "rows rather than built from V5_LAYOUT (its registry entry has no "
        "v5_code), so it sits outside the generic OPTIONAL_MODULE_SHEETS loop "
        "above and needs its own gate before _extract_scorp_sheet(wb) runs.",
    ),

    # ── Soft dependencies: another module's output is shaped by this toggle ──
    ("src/reporting/sheets_summary_builder.py", "build_sheet1", "market_luck_stress_test"): (
        SOFT, "executive_summary", (),
        "Suppresses the worst-case-ending-wealth and model-risk headline rows "
        "rather than showing a misleading 0%.",
    ),
    ("src/reporting/sheets_summary_builder.py", "build_sheet1", "social_security_timing"): (
        SOFT, "executive_summary", (),
        "Suppresses the optimal claim-age headline.",
    ),
    ("src/reporting/sheets_projection_charts.py", "build_sheet8",
     "market_luck_stress_test"): (
        SOFT, "charts_dashboard", (),
        "Embeds the percentile-band chart only when Monte Carlo ran.",
    ),
    ("src/reporting/workbook_builder.py", "build_sheet27_planning_levers",
     "market_luck_stress_test"): (
        SOFT, "planning_levers_echo", (),
        "The model-anchor block shows 'Not run (module off)' in the Monte Carlo "
        "success row, keeping the row so the lever formulas' fixed cell "
        "references below it do not shift.",
    ),
    ("src/spending_tracker.py", "_insurance_policy_premium_sum",
     "_existing_life_insurance_module_enabled"): (
        SOFT, "cash_flow", ("existing_life_insurance",),
        "An Auto policy's real premium supersedes the typed auto_insurance "
        "budget line only while Existing Life Insurance is on. Reads the CSV by "
        "hand instead of calling the accessor -- see this module's own note.",
    ),

    # ── Engine participation: the toggle moves the projection ────────────────
    # W7 replaced this file's single raw c['opt'] read with two literal
    # module_enabled() calls, so the sweep now sees each key itself and
    # keys_read is empty for both (see _engine_keys below).
    ("src/projection_stages/deterministic_engine.py",
     "run_deterministic_projection_stage", "equity_compensation"): (
        ENGINE, None, (),
        "Grant vest/exercise income and the ISO minimum-tax credit carry. "
        "Still ANDed with a non-empty c['equity_comp'], so the toggle alone "
        "cannot conjure grants a plan does not have.",
    ),
    ("src/projection_stages/deterministic_engine.py",
     "run_deterministic_projection_stage", "disability_income_insurance"): (
        ENGINE, None, (),
        "The DI benefit stream, which zeroes earned income for the benefit "
        "period. Guarded downstream by income.py's own `simulate_year and "
        "policies` check, so the toggle alone changes nothing on a plan that "
        "configures no disability event.",
    ),
    ("src/after_tax.py", "business_taxable_estate_value", RAW_OPT): (
        ENGINE, None, ("business_succession",),
        "Adds the owner's projected business interest to the taxable estate, "
        "changing computed estate tax and not merely sheet 34's existence.",
    ),
}


# ── The sweep ────────────────────────────────────────────────────────────────

def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    """Map every line in a function body to that function's name.

    Nested/inner functions win over their enclosing one, because that is the
    name a reader looking for the site will search for.
    """
    spans: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            for line in range(node.lineno, end + 1):
                spans[line] = node.name
    return spans


def _toggle_sites(path: Path) -> list[tuple[str, str, str]]:
    """``(file, function, toggle)`` for every toggle read in ``path``."""
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    where = _enclosing_functions(tree)
    found: list[tuple[str, str, str]] = []

    for node in ast.walk(tree):
        fn = where.get(getattr(node, "lineno", -1), "<module>")

        # `c['opt']` -- a READ only. The loader's `c['opt'] = {...}` is an
        # ast.Store subscript and drops out here, by context rather than by a
        # named exemption, so it cannot quietly become a read.
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value == "opt":
                found.append((rel, fn, RAW_OPT))
            continue

        if not isinstance(node, ast.Call):
            continue

        # `<anything>.get('opt')` -- the same read, spelled defensively.
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "opt"):
            found.append((rel, fn, RAW_OPT))
            continue

        # `module_enabled(c, '<key>')`, and any hand-rolled `*_module_enabled`.
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else "")
        if not name.endswith("module_enabled"):
            continue
        if name != "module_enabled":
            # A bespoke reader names its own module in its name; the fixture
            # records which key it actually reads.
            found.append((rel, fn, name))
            continue
        key = node.args[1] if len(node.args) > 1 else None
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            found.append((rel, fn, key.value))
        else:
            found.append((rel, fn, DYNAMIC))

    return found


def sweep_src() -> set[tuple[str, str, str]]:
    sites: set[tuple[str, str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        sites.update(_toggle_sites(path))
    return sites


# ── The assertions ───────────────────────────────────────────────────────────

def test_the_sweep_finds_exactly_the_declared_call_sites():
    """No toggle read may appear in ``src/`` without a verdict recorded above.

    This is the drift guard. A new call site is not a test failure because new
    call sites are bad -- it is a prompt to decide, once, which of the four
    verdicts it carries, and to add the declaration the answer implies.
    """
    found = sweep_src()
    declared = set(DECLARED_SITES)

    undeclared = found - declared
    assert not undeclared, (
        "New optional-module toggle read(s) in src/ with no classification:\n  "
        + "\n  ".join(f"{f}:{fn}() reads {k}" for f, fn, k in sorted(undeclared))
        + "\n\nDecide which verdict each one carries and add it to "
          "DECLARED_SITES in this file:\n"
          "  own_gate -- the site decides whether its own module runs;\n"
          "  soft     -- it shapes another module's output, so that module "
          "must declare degrades_without;\n"
          "  engine   -- it changes the projection, so the module named must "
          "declare engine_participation=True;\n"
          "  accessor -- it is module_catalog's own gate implementation."
    )

    stale = declared - found
    assert not stale, (
        "DECLARED_SITES lists toggle read(s) that no longer exist in src/:\n  "
        + "\n  ".join(f"{f}:{fn}() reads {k}" for f, fn, k in sorted(stale))
        + "\n\nIf the code moved, update the entry; if it is gone, delete it "
          "(and check whether the declaration backing it is now unused)."
    )


@pytest.mark.parametrize(
    "site",
    [s for s, v in DECLARED_SITES.items() if v[0] == SOFT],
    ids=lambda s: f"{Path(s[0]).stem}.{s[1]}[{s[2]}]",
)
def test_soft_sites_are_declared_on_the_consuming_module(site):
    """A module whose output another module's toggle shapes must say so.

    This is the assertion the whole workstream exists for: without it, the fact
    that Exec Summary quietly drops two headline rows when Monte Carlo is off
    lives only in a comment next to an `if`, where no UI can find it.
    """
    verdict, consumer, keys, why = DECLARED_SITES[site]
    _path, _fn, toggle = site
    read_keys = keys or (toggle,)

    assert consumer in mc.CATALOG, f"{site}: unknown consuming module {consumer!r}"
    module = mc.CATALOG[consumer]
    soft = {dep for dep, _loses in module.degrades_without}

    for key in read_keys:
        assert key in soft or key in module.requires_outputs, (
            f"{site[0]}:{site[1]}() gates {consumer!r}'s output on the "
            f"{key!r} toggle, but {consumer!r} declares neither "
            f"degrades_without={key!r} nor requires_outputs={key!r}.\n"
            f"Site's own reason: {why}\n"
            f"Add degrades_without=(_soft({key!r}, '<what is lost>'),) to "
            f"CATALOG[{consumer!r}] -- requires_outputs is only right if "
            f"{consumer!r} genuinely cannot build at all without it, since "
            f"that auto-enables {key!r} behind the user's back."
        )


def _engine_keys(site: tuple[str, str, str]) -> tuple[str, ...]:
    """The module keys an engine site reads.

    Two spellings reach the same place. A site that reads the whole ``opt``
    mapping cannot name its keys to the parse tree, so the fixture carries them
    in ``keys_read``; a site that calls ``module_enabled(c, 'literal')`` names
    the key in the call, so the sweep already has it and ``keys_read`` is empty.
    Before W7 the engine used the first spelling and after it the second, which
    is exactly the migration this helper exists to absorb -- the invariant
    ("every engine site's keys are declared `engine_participation`") is the same
    either way, and must not weaken just because the read got more honest.
    """
    _v, _c, keys, _w = DECLARED_SITES[site]
    return keys or (site[2],)


@pytest.mark.parametrize(
    "site",
    [s for s, v in DECLARED_SITES.items() if v[0] == ENGINE],
    ids=lambda s: Path(s[0]).stem,
)
def test_engine_sites_declare_engine_participation(site):
    """The projection reading a toggle is what `engine_participation` means."""
    _verdict, _consumer, _keys, why = DECLARED_SITES[site]
    keys = _engine_keys(site)
    assert keys, f"{site}: an engine site must record which toggles it reads"
    for key in keys:
        assert key in mc.CATALOG, f"{site}: unknown module {key!r}"
        assert mc.CATALOG[key].engine_participation, (
            f"{site[0]}:{site[1]}() reads the {key!r} toggle and changes the "
            f"projection with it, but CATALOG[{key!r}].engine_participation is "
            f"False.\nSite's own reason: {why}"
        )


def test_engine_participation_is_claimed_only_where_the_engine_reads_it():
    """The reverse direction: no module claims to move the projection unless a
    swept engine site actually reads it.

    Without this the flag is free to be aspirational, which is the state #330
    §3.1's F3 is trying to leave.
    """
    read_by_engine = {
        key for site, (verdict, _c, _keys, _w) in DECLARED_SITES.items()
        if verdict == ENGINE for key in _engine_keys(site)
    }
    assert set(mc.engine_participants()) == read_by_engine


@pytest.mark.parametrize(
    "site",
    [s for s, v in DECLARED_SITES.items() if v[2]],
    ids=lambda s: f"{Path(s[0]).stem}.{s[1]}",
)
def test_recorded_keys_still_appear_in_their_file(site):
    """Keys the parse tree cannot see are checked for presence instead.

    Two kinds of site name their module somewhere the sweep cannot reach it: a
    raw `opt` mapping read (the key is pulled out on a later line) and a
    hand-rolled reader. The fixture records the keys by hand, so this pins them
    to the file -- enough to catch a module rename that leaves this fixture
    describing a toggle the file no longer mentions.
    """
    path, _fn, _toggle = site
    keys = DECLARED_SITES[site][2]
    text = (ROOT / path).read_text(encoding="utf-8")
    for key in keys:
        assert key in text, (
            f"{path} is recorded as reading the {key!r} toggle, but that "
            f"string does not appear in the file. Was the module renamed?"
        )


def test_every_soft_declaration_is_backed_by_a_swept_call_site():
    """No `degrades_without` without a call site that justifies it.

    The field is a description of what the code does, so a declaration nothing
    reads is either dead or aspirational -- and both are how a hand-maintained
    twin starts.
    """
    swept: set[tuple[str, str]] = set()
    for site, (verdict, consumer, keys, _why) in DECLARED_SITES.items():
        if verdict != SOFT:
            continue
        for key in (keys or (site[2],)):
            swept.add((consumer, key))

    declared = {
        (key, dep)
        for key, m in mc.CATALOG.items()
        for dep, _loses in m.degrades_without
    }
    assert declared == swept, (
        "degrades_without declarations and swept soft call sites disagree.\n"
        f"  declared but never read: {sorted(declared - swept)}\n"
        f"  read but never declared: {sorted(swept - declared)}"
    )
