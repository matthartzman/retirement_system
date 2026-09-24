"""W-B / #334 (Task B2): IRMAA threshold and surcharge indexing lives only in
``src/tax_kernel.py``. The retired 2% ``irmaa_annual_inflator`` input
(``c['irmaa_inflator']``), the Monte Carlo ``irmaa_index_by_year`` path and the
user-overridable ``irmaa_base`` threshold must not reappear anywhere in src/.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


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
