from __future__ import annotations

"""Versioned tax-law dataset loader for v11.

Tax constants are loaded from the shipped reference.db (source: reference_src/tax_law_v10.json).  The engine can
still call older compatibility helpers, but this module is the single typed data
source for new code and tests; it has no embedded numeric fallbacks.
"""

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class TaxLawValue:
    jurisdiction: str
    filing_status: str
    name: str
    value: float
    effective_year: int
    expires_year: int | None = None
    source: str = "local_dataset"
    status: str = "assumption"


@dataclass(frozen=True)
class TaxBracket:
    jurisdiction: str
    filing_status: str
    bracket_type: str
    lower: float
    upper: float | None
    rate: float
    effective_year: int
    expires_year: int | None = None
    source: str = "local_dataset"
    status: str = "assumption"


@dataclass(frozen=True)
class TaxLawDataset:
    schema: str
    version: str
    generated_from: str
    values: tuple[TaxLawValue, ...]
    brackets: tuple[TaxBracket, ...] = ()

    def lookup(self, name: str, year: int, jurisdiction: str = "US", filing_status: str = "MFJ") -> TaxLawValue:
        matches = [v for v in self.values if v.name == name and v.jurisdiction == jurisdiction and v.filing_status == filing_status and v.effective_year <= year and (v.expires_year is None or year <= v.expires_year)]
        if not matches and filing_status != "MFJ":
            matches = [v for v in self.values if v.name == name and v.jurisdiction == jurisdiction and v.filing_status == "MFJ" and v.effective_year <= year and (v.expires_year is None or year <= v.expires_year)]
        if not matches:
            raise KeyError(f"No tax law value for {jurisdiction}/{filing_status}/{name}/{year}")
        return sorted(matches, key=lambda v: v.effective_year)[-1]

    def bracket_table(self, bracket_type: str, year: int, jurisdiction: str = "US", filing_status: str = "MFJ") -> tuple[TaxBracket, ...]:
        matches = [b for b in self.brackets if b.bracket_type == bracket_type and b.jurisdiction == jurisdiction and b.filing_status == filing_status and b.effective_year <= year and (b.expires_year is None or year <= b.expires_year)]
        if not matches and filing_status != "MFJ":
            matches = [b for b in self.brackets if b.bracket_type == bracket_type and b.jurisdiction == jurisdiction and b.filing_status == "MFJ" and b.effective_year <= year and (b.expires_year is None or year <= b.expires_year)]
        if not matches:
            raise KeyError(f"No {bracket_type} brackets for {jurisdiction}/{filing_status}/{year}")
        best_year = max(b.effective_year for b in matches)
        return tuple(sorted([b for b in matches if b.effective_year == best_year], key=lambda b: b.lower))

    def as_engine_tables(self, year: int) -> dict[str, Any]:
        statuses = sorted({v.filing_status for v in self.values if v.jurisdiction == "US"} | {b.filing_status for b in self.brackets if b.jurisdiction == "US"})
        return {
            "standard_deduction": {s: self.lookup("standard_deduction", year, filing_status=s).value for s in statuses if any(v.name == "standard_deduction" and v.filing_status == s for v in self.values)},
            "standard_deduction_over65": {s: self.lookup("standard_deduction_over65", year, filing_status=s).value for s in statuses if any(v.name == "standard_deduction_over65" and v.filing_status == s for v in self.values)},
            "niit_threshold": {s: self.lookup("niit_threshold", year, filing_status=s).value for s in statuses if any(v.name == "niit_threshold" and v.filing_status == s for v in self.values)},
            "ordinary_brackets": {s: [(b.lower, float("inf") if b.upper is None else b.upper, b.rate) for b in self.bracket_table("ordinary", year, filing_status=s)] for s in statuses if any(b.bracket_type == "ordinary" and b.filing_status == s for b in self.brackets)},
            "ltcg_brackets": {s: {"zero_top": self.lookup("ltcg_0pct_top", year, filing_status=s).value, "fifteen_top": self.lookup("ltcg_15pct_top", year, filing_status=s).value} for s in statuses if any(v.name == "ltcg_0pct_top" and v.filing_status == s for v in self.values)},
            "irmaa_tiers": {s: self._irmaa_tiers(year, filing_status=s) for s in statuses if any(v.name.startswith("irmaa_tier") and v.filing_status == s for v in self.values)},
            "ss_wage_base": self.lookup("ss_wage_base", year, filing_status="MFJ").value if any(v.name == "ss_wage_base" for v in self.values) else None,
            "salt_cap": self.lookup("salt_cap", year, filing_status="MFJ").value if any(v.name == "salt_cap" for v in self.values) else None,
        }

    def latest_value(self, name: str, jurisdiction: str = "US", filing_status: str = "MFJ") -> TaxLawValue:
        """The row with the latest ``effective_year`` for ``name`` (the
        dataset's current knowledge), regardless of the projection year."""
        matches = [v for v in self.values if v.name == name and v.jurisdiction == jurisdiction and v.filing_status == filing_status]
        if not matches:
            raise KeyError(f"No tax law value for {jurisdiction}/{filing_status}/{name}")
        return sorted(matches, key=lambda v: v.effective_year)[-1]

    def lookup_or_earliest(self, name: str, year: int, jurisdiction: str = "US", filing_status: str = "MFJ") -> TaxLawValue:
        """``lookup`` but, for a year before the earliest dated row, the
        earliest row (documented assumption: an older table is not held)."""
        try:
            return self.lookup(name, year, jurisdiction=jurisdiction, filing_status=filing_status)
        except KeyError:
            matches = [v for v in self.values if v.name == name and v.jurisdiction == jurisdiction and v.filing_status == filing_status]
            if not matches:
                raise
            return sorted(matches, key=lambda v: v.effective_year)[0]

    def aca_applicable_pct_table(self, regime: str, year: int) -> dict[str, Any]:
        """WI-307 / FIN-007: the dated ACA applicable-percentage table for
        ``regime`` ("enhanced" or "original" §36B) in force in ``year``.

        Rows are ``aca_applicable_pct_<regime>_band<N>_{fpl_floor,initial,final}``
        (N = 1, 2, ... contiguous; a band runs from its floor to the next
        band's floor, or to ``max_fpl`` for the last band, and the required
        contribution interpolates linearly from ``initial`` to ``final``), plus
        ``_max_fpl``, ``_credit_above_max`` (1 = credit continues above
        ``max_fpl`` at ``_above_max_pct``; 0 = no credit, the 400% FPL cliff)
        and, when the credit continues, ``_above_max_pct``. A year after the
        latest dated row uses that row; a year before the earliest uses the
        earliest (both documented assumptions).
        """
        prefix = f"aca_applicable_pct_{regime}"
        bands: list[tuple[float, float, float]] = []
        for idx in range(1, 50):
            base = f"{prefix}_band{idx}"
            if not any(v.name == f"{base}_fpl_floor" for v in self.values):
                break
            bands.append((
                float(self.lookup_or_earliest(f"{base}_fpl_floor", year).value),
                float(self.lookup_or_earliest(f"{base}_initial", year).value),
                float(self.lookup_or_earliest(f"{base}_final", year).value),
            ))
        if not bands:
            raise KeyError(f"No ACA applicable-percentage table for regime {regime!r}")
        credit_above = bool(float(self.lookup_or_earliest(f"{prefix}_credit_above_max", year).value))
        return {
            "bands": tuple(sorted(bands)),
            "max_fpl": float(self.lookup_or_earliest(f"{prefix}_max_fpl", year).value),
            "credit_above_max": credit_above,
            "above_max_pct": float(self.lookup_or_earliest(f"{prefix}_above_max_pct", year).value) if credit_above else None,
        }

    def _irmaa_tiers(self, year: int, filing_status: str = "MFJ") -> tuple[tuple[float, float, float], ...]:
        """Build the ordered IRMAA tier table for one filing status.

        `lookup()` falls back to MFJ values when a filing status has no
        explicit entry for a given key, which is the desired behavior for
        most tables (e.g. standard deduction overrides). For IRMAA tiers it
        is wrong: MFS is statutorily defined with only 2 tiers, but the MFJ
        fallback silently appended MFJ's tier3-5 rows once MFS ran out of its
        own tiers, producing a non-monotonic threshold list. So here we stop
        as soon as the filing status has no *own* entry for the next tier,
        rather than falling through to MFJ's table.
        """
        tiers: list[tuple[float, float, float]] = []
        for idx in range(1, 10):
            name_threshold = f"irmaa_tier{idx}_threshold"
            has_own_tier = any(
                v.name == name_threshold and v.filing_status == filing_status
                for v in self.values
            )
            if not has_own_tier:
                break
            try:
                threshold = self.lookup(name_threshold, year, filing_status=filing_status).value
                part_b = self.lookup(f"irmaa_tier{idx}_part_b_surcharge_monthly", year, filing_status=filing_status).value
                part_d = self.lookup(f"irmaa_tier{idx}_part_d_surcharge_monthly", year, filing_status=filing_status).value
            except KeyError:
                break
            tiers.append((threshold, part_b, part_d))
        return tuple(tiers)


def load_tax_law_dataset() -> TaxLawDataset:
    """The tax-law dataset from the shipped reference.db (built fresh on every call)."""
    from .stores.ref_getters.tax_law import tax_law_dataset
    return tax_law_dataset()


_DEFAULT_DATASET_CACHE: list[TaxLawDataset] = []


def default_tax_law_dataset() -> TaxLawDataset:
    """The default dataset, loaded once per process (read-only use)."""
    if not _DEFAULT_DATASET_CACHE:
        _DEFAULT_DATASET_CACHE.append(load_tax_law_dataset())
    return _DEFAULT_DATASET_CACHE[0]


def aca_enhanced_subsidies_through_year_default() -> int:
    """WI-307 / FIN-007: last enhanced-PTC year used when a plan leaves
    Wellness/ACA Premium Tax Credit/enhanced_subsidies_through_year blank.
    Read from the latest dated ``aca_enhanced_subsidies_through_year`` row;
    see that row's ``status``/``source`` for how far it is verified."""
    return int(default_tax_law_dataset().latest_value("aca_enhanced_subsidies_through_year").value)


def dataset_freshness_summary() -> dict[str, Any]:
    from .stores.ref_getters.tax_law import tax_law_freshness
    return tax_law_freshness()
