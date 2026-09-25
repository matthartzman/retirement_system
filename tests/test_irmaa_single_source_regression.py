"""W-B / #334 (Task B2): IRMAA threshold and surcharge indexing lives only in
``src/tax_kernel.py``. The retired 2% ``irmaa_annual_inflator`` input
(``c['irmaa_inflator']``), the Monte Carlo ``irmaa_index_by_year`` path and the
user-overridable ``irmaa_base`` threshold must not reappear anywhere in src/.

Task B4 (final whole-branch review finding): a tier's DOLLAR AMOUNT is also
single-sourced. ``src/hsa_schedule.py`` used to read ``IRMAA_TIERS_BASE_YEAR``
directly and compute raw 2025-dollar ``(part_b + part_d) * 12`` tier steps,
missing the Medicare-inflation indexing (``med_inf``/``partd_inf``) and dime
rounding that ``tax_kernel.irmaa_surcharge`` applies -- a second, silently
stale IRMAA-dollar model. It now calls ``tax_kernel.irmaa_tier_monthly``
instead. ``test_no_raw_irmaa_tier_dollar_arithmetic_outside_kernel`` guards
against that pattern reappearing anywhere else in src/.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# Files allowed to hold the raw base-year table / build it from source data.
# ``tax_kernel.py`` is the one place permitted to turn those raw dollars into
# a real-year surcharge; ``taxes.py`` and ``tax_law.py`` only assemble the
# base-year table itself (no *12 annualization, no inflation factor).
_RAW_TABLE_FILES = {"tax_kernel.py", "taxes.py", "tax_law.py"}


def _hits(pattern):
    return sorted(
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if re.search(pattern, p.read_text(encoding="utf-8"))
    )


def test_no_irmaa_inflator_outside_kernel():
    hits = _hits(r"irmaa_inflator|irmaa_index_by_year")
    assert hits == [], hits


def test_no_irmaa_base_input_in_src():
    hits = _hits(r"\birmaa_base\b")
    assert hits == [], hits


def test_no_raw_irmaa_tier_dollar_arithmetic_outside_kernel():
    """No file outside ``tax_kernel.py`` (and the table-builders above) may
    multiply a ``part_b``/``part_d``-style pair by 12 directly -- that is the
    exact shape of the stale, unindexed tier-dollar bug this file's Task B4
    fixed in ``hsa_schedule.py``. A correct caller instead calls
    ``tax_kernel.irmaa_tier_monthly``/``irmaa_surcharge``.
    """
    pattern = re.compile(
        r"part_?[bd]\w*\s*[,)]?\s*[+)]\s*.{0,40}?part_?[bd]\w*.{0,10}?\)\s*\*\s*12",
        re.IGNORECASE,
    )
    hits = []
    for p in SRC.rglob("*.py"):
        rel = str(p.relative_to(SRC))
        if rel in _RAW_TABLE_FILES:
            continue
        if pattern.search(p.read_text(encoding="utf-8")):
            hits.append(rel)
    assert hits == [], hits
