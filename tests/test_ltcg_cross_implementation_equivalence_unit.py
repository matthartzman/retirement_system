"""Do the three (formerly independent) LTCG bracket-stacking call sites agree?

System review 2026-08-31, finding A6 / Wave 1 item 1.12 / Wave 2 item 2.1.

**History.** This file originally started as a DIAGNOSTIC ONLY test (no src/
edit) written to answer, with numbers, whether the 0%/15%/20% LTCG
bracket-stacking rule's three independent implementations --
``src.core.ltcg_tax_on_gain`` (inflating bracket tops using
``c['irmaa_inflator']`` compounded from ``c['plan_start']``),
``run_deterministic_projection_stage``'s nested ``_ltcg_tax_on_gain_path`` /
``_bracket_factor_for_year`` (inflating using ``c['brk_inf']`` compounded
from ``src.taxes.FEDERAL_BRACKETS_VALUE_YEAR``), and
``src.tlh._ltcg_marginal_rate`` -- actually disagreed in practice, or were
merely a tidiness issue. They disagreed substantially: up to ~$7,869 over a
30-year horizon at one real fixture's configured rates (see the retained
scenario tests below, now flipped from "diverge" to "agree" assertions).

**Fix (Wave 2 item 2.1).** ``src/tax_kernel.py`` is now the single canonical
implementation. Financial sign-off: the unified convention is
``brk_inf``/``fed_tax_bracket_inflator``, compounded from
``taxes.FEDERAL_BRACKETS_VALUE_YEAR`` -- the engine's pre-existing
convention. ``core.ltcg_tax_on_gain`` and the engine's
``_ltcg_tax_on_gain_path`` are now both thin call sites into
``tax_kernel.ltcg_tax_on_gain``, so they are expected to agree exactly
(irrespective of ``irmaa_inflator``, which the kernel does not consult for
LTCG at all) rather than merely "close enough". This file is kept -- rather
than deleted -- as the regression guard against the fix regressing: it still
extracts the engine's real nested-closure source by AST (not a transcribed
copy), so it fails loudly if the engine's internal structure changes instead
of silently drifting.

Method
------
``_bracket_factor_for_year``/``_ltcg_tax_on_gain_path`` are nested closures
with no module-level name -- they only exist inside the 3,000+ line
``run_deterministic_projection_stage`` function and are never returned or
exposed. To exercise the REAL current source (not a hand-transcribed copy of
it, which would just be a fourth implementation and prove nothing about the
other three), this file extracts their AST source segments directly out of
``inspect.getsource(run_deterministic_projection_stage)`` and execs them into
an isolated namespace that supplies the same free variables (``c``, the
module's ``_ar`` alias for ``src.core``, and ``TAX_BASE_YEAR``) the real
closures rely on. If the engine's source for either closure is ever renamed
or restructured, ``_extract_engine_ltcg_fn`` fails loudly (AssertionError)
rather than silently drifting from the real implementation.

``_ltcg_marginal_rate`` returns a marginal *rate*, not a total tax dollar
figure, so it is not directly comparable to the other two. To make it
comparable, ``_tlh_reconstructed_tax`` calls it three times -- once per band
(0%, 15%, 20%) at the cumulative income point where that band begins -- and
sums rate * band-width, using the exact same stacking order (ordinary income
fills from zero, then gain stacks on top) that ``ltcg_tax_on_gain`` and
``_ltcg_tax_on_gain_path`` use inline. This reconstruction is itself verified
below (``test_tlh_reconstruction_matches_core_when_given_cores_own_bracket_factor``)
to reproduce ``core.ltcg_tax_on_gain`` exactly when fed the same
bracket_factor and bracket tops -- i.e. tlh.py's own stacking arithmetic is
not an independent source of disagreement; only the bracket_factor a caller
feeds it can be.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

import src.core as core
import src.projection_stages.deterministic_engine as de
import src.taxes as taxes
from src.tlh import _ltcg_marginal_rate

FEDERAL_BRACKETS_VALUE_YEAR = taxes.FEDERAL_BRACKETS_VALUE_YEAR
LTCG_0_TOP = 96_700.0
LTCG_15_TOP = 600_050.0

GAINS = [1_000.0, 30_000.0, 150_000.0, 400_000.0, 900_000.0]
ORDINARY_INCOMES = [0.0, 40_000.0, 90_000.0, 150_000.0, 300_000.0]
# Offsets from plan_start -- exercises near-term, mid-horizon and long-horizon
# years, where compounding-index divergence (if any) grows largest.
YEAR_OFFSETS = [0, 5, 10, 20, 30]


def _extract_nested_source(outer_func, name: str) -> str:
    """Pull the exact source of a nested ``def`` out of ``outer_func`` by AST,
    so the test exercises the real current implementation rather than a
    transcribed copy of it."""
    src_text = textwrap.dedent(inspect.getsource(outer_func))
    tree = ast.parse(src_text)
    outer_def = tree.body[0]
    for node in ast.walk(outer_def):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(src_text, node)
            assert segment is not None, name
            return textwrap.dedent(segment)
    raise AssertionError(
        f"{name!r} not found as a nested def inside {outer_func.__name__}; "
        "the engine's internal structure changed -- update this extractor."
    )


def _extract_engine_ltcg_fn(c: dict):
    """Build a standalone callable out of the engine's real, un-exported
    ``_ltcg_tax_on_gain_path``/``_bracket_factor_for_year`` closures, bound to
    ``c``."""
    bf_src = _extract_nested_source(de.run_deterministic_projection_stage, "_bracket_factor_for_year")
    ltcg_src = _extract_nested_source(de.run_deterministic_projection_stage, "_ltcg_tax_on_gain_path")
    # Post-2.1, both nested closures are one-line delegations to `_tk`
    # (module-level alias for src.tax_kernel) rather than self-contained
    # arithmetic, so the exec namespace must supply it.
    namespace = {"c": c, "TAX_BASE_YEAR": de.TAX_BASE_YEAR, "_ar": de._ar, "_tk": de._tk}
    exec(compile(bf_src + "\n" + ltcg_src, "<deterministic_engine_ltcg_extract>", "exec"), namespace)
    return namespace["_ltcg_tax_on_gain_path"]


def _tlh_reconstructed_tax(gain: float, ordinary_income: float, bracket_factor: float,
                            ltcg_0_top: float = LTCG_0_TOP, ltcg_15_top: float = LTCG_15_TOP) -> float:
    """Total LTCG tax on ``gain`` as implied by tlh.py's real
    ``_ltcg_marginal_rate``, reconstructed band-by-band (see module docstring)."""
    top0 = ltcg_0_top * bracket_factor
    top15 = ltcg_15_top * bracket_factor
    base = max(0.0, ordinary_income)
    remaining = float(gain)
    in0 = min(remaining, max(0.0, top0 - base)); remaining -= in0
    in15 = min(remaining, max(0.0, top15 - max(base, top0))); remaining -= in15
    rest = max(0.0, remaining)
    tax = 0.0
    if in0 > 0:
        tax += in0 * _ltcg_marginal_rate(base, 0.0, ltcg_0_top, ltcg_15_top, bracket_factor, False)
    if in15 > 0:
        tax += in15 * _ltcg_marginal_rate(base, in0, ltcg_0_top, ltcg_15_top, bracket_factor, False)
    if rest > 0:
        tax += rest * _ltcg_marginal_rate(base, in0 + in15, ltcg_0_top, ltcg_15_top, bracket_factor, False)
    return tax


def _grid():
    for gain in GAINS:
        for oi in ORDINARY_INCOMES:
            for offset in YEAR_OFFSETS:
                yield gain, oi, offset


def _run_case(*, irmaa_inflator: float, brk_inf: float, plan_start: int):
    """For one (irmaa_inflator, brk_inf, plan_start) config, compute all three
    implementations across the full grid and return the per-case results plus
    the worst absolute divergence between core.py and the engine."""
    c = {
        "ltcg_0_top": LTCG_0_TOP,
        "ltcg_15_top": LTCG_15_TOP,
        "irmaa_inflator": irmaa_inflator,
        "brk_inf": brk_inf,
        "plan_start": plan_start,
    }
    engine_ltcg_fn = _extract_engine_ltcg_fn(c)

    rows = []
    for gain, oi, offset in _grid():
        year = plan_start + offset
        core_tax = core.ltcg_tax_on_gain(c, gain, oi, year)
        engine_tax = engine_ltcg_fn(gain, oi, year)

        core_bf = (1.0 + irmaa_inflator) ** (year - plan_start)
        tlh_tax_core_bf = _tlh_reconstructed_tax(gain, oi, core_bf)

        rows.append({
            "gain": gain, "ordinary_income": oi, "year": year,
            "core_tax": core_tax, "engine_tax": engine_tax,
            "tlh_tax_core_bf": tlh_tax_core_bf,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Control: tlh.py's stacking arithmetic itself is not a source of disagreement
# ─────────────────────────────────────────────────────────────────────────────

def test_tlh_reconstruction_matches_core_when_given_cores_own_bracket_factor():
    """tlh._ltcg_marginal_rate, reconstructed into a total tax, must equal
    core.ltcg_tax_on_gain exactly when fed the SAME bracket_factor and bracket
    tops core.py itself would use. This isolates the disagreement (if any) to
    the *inflation index each implementation independently derives*, not to
    tlh.py's stacking math being wrong.

    Post-2.1: "core's own bracket factor" is ``tax_kernel.bracket_factor_for_year``
    (brk_inf, compounded from the brackets' statutory value year) -- core.py no
    longer derives its own irmaa_inflator/plan_start-based factor."""
    import src.tax_kernel as tax_kernel
    brk_inf, plan_start = 0.02, 2026
    for gain, oi, offset in _grid():
        year = plan_start + offset
        c = {"ltcg_0_top": LTCG_0_TOP, "ltcg_15_top": LTCG_15_TOP,
             "brk_inf": brk_inf, "plan_start": plan_start}
        core_tax = core.ltcg_tax_on_gain(c, gain, oi, year)
        bf = tax_kernel.bracket_factor_for_year(c, year)
        tlh_tax = _tlh_reconstructed_tax(gain, oi, bf)
        assert tlh_tax == pytest.approx(core_tax, abs=1e-6), (gain, oi, year)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario A -- same rate, same index base year: true control
# ─────────────────────────────────────────────────────────────────────────────

def test_core_and_engine_agree_when_rate_and_index_base_year_both_match():
    """When irmaa_inflator == brk_inf AND plan_start == FEDERAL_BRACKETS_VALUE_YEAR
    (so both implementations compound from the same starting point at the same
    rate), the two independent implementations must produce identical dollars.
    This is the strict control: it proves the underlying stacking algorithm is
    identical in both places, so any divergence found elsewhere in this file
    is attributable purely to the differing inflation *index*/*base year*
    conventions, not to a second, unrelated bug in the formula itself."""
    rate = 0.02
    rows = _run_case(irmaa_inflator=rate, brk_inf=rate, plan_start=FEDERAL_BRACKETS_VALUE_YEAR)
    for row in rows:
        assert row["engine_tax"] == pytest.approx(row["core_tax"], abs=1e-6), row


# ─────────────────────────────────────────────────────────────────────────────
# Scenario B -- same rate, realistic plan_start (one year after the brackets'
# value year, as essentially every real plan is). Pre-2.1 this was enough,
# on its own, to make core.py and the engine disagree (the base-year offset).
# Post-2.1 both delegate to the same kernel function, so they must now agree.
# ─────────────────────────────────────────────────────────────────────────────

def test_core_and_engine_agree_from_shared_kernel_despite_index_base_year_offset():
    """Pre-2.1: core.py compounded irmaa_inflator from ``plan_start``; the
    engine compounded brk_inf from ``taxes.FEDERAL_BRACKETS_VALUE_YEAR`` (a
    fixed statutory-data vintage, currently one year behind a plan_start of
    2026). Even with irmaa_inflator == brk_inf, a real plan (plan_start !=
    brackets' value year) made the two bracket-inflation factors differ by a
    full extra year of compounding baked in from year one. Post-2.1, both
    ``core.ltcg_tax_on_gain`` and the engine's ``_ltcg_tax_on_gain_path`` are
    thin call sites into ``tax_kernel.ltcg_tax_on_gain``, which does not
    consult ``irmaa_inflator`` for LTCG at all -- so this scenario, which
    used to be the base-year-offset repro case, must now produce identical
    dollars regardless of what ``irmaa_inflator`` is set to."""
    rate = 0.02
    plan_start = FEDERAL_BRACKETS_VALUE_YEAR + 1  # e.g. 2026 when brackets are vintage 2025
    rows = _run_case(irmaa_inflator=rate, brk_inf=rate, plan_start=plan_start)

    for row in rows:
        assert row["engine_tax"] == pytest.approx(row["core_tax"], abs=1e-6), row


# ─────────────────────────────────────────────────────────────────────────────
# Scenario C -- divergent irmaa_inflator/brk_inf AND realistic plan_start,
# mirroring a real fixture's actual configured values (irmaa_inflator=0.02,
# brk_inf=0.028). This was the worst-case, actually-shipped pre-2.1
# divergence (~$7,869 over a 30-year horizon); post-2.1 the kernel ignores
# irmaa_inflator for LTCG entirely, so core.py and the engine must agree.
# ─────────────────────────────────────────────────────────────────────────────

def test_core_and_engine_agree_from_shared_kernel_with_real_fixture_inflator_values():
    """One real fixture configures irmaa_inflator=0.02 and brk_inf=0.028 (see
    src/data_io.py's API-config defaults). Locks in that the tax-kernel
    extraction (item 2.1) actually closed this gap end to end, not just in
    the kernel's own unit tests."""
    plan_start = FEDERAL_BRACKETS_VALUE_YEAR + 1
    rows = _run_case(irmaa_inflator=0.02, brk_inf=0.028, plan_start=plan_start)

    for row in rows:
        assert row["engine_tax"] == pytest.approx(row["core_tax"], abs=1e-6), row
    max_abs_diff = max(abs(row["engine_tax"] - row["core_tax"]) for row in rows)
    assert max_abs_diff < 1e-6, (
        f"expected core.py and the engine to agree exactly post-kernel-extraction; "
        f"worst was ${max_abs_diff:.2f}"
    )
