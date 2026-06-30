from __future__ import annotations

"""Versioned tax-law dataset loader for v10.

Tax constants are loaded from reference_data/tax_law_v10.json.  The engine can
still call older compatibility helpers, but this module is the single typed data
source for new code and tests; it has no embedded numeric fallbacks.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAX_LAW_JSON = PROJECT_ROOT / "reference_data" / "tax_law_v10.json"


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

    def _irmaa_tiers(self, year: int, filing_status: str = "MFJ") -> tuple[tuple[float, float, float], ...]:
        tiers: list[tuple[float, float, float]] = []
        for idx in range(1, 10):
            try:
                threshold = self.lookup(f"irmaa_tier{idx}_threshold", year, filing_status=filing_status).value
                part_b = self.lookup(f"irmaa_tier{idx}_part_b_surcharge_monthly", year, filing_status=filing_status).value
                part_d = self.lookup(f"irmaa_tier{idx}_part_d_surcharge_monthly", year, filing_status=filing_status).value
            except KeyError:
                continue
            tiers.append((threshold, part_b, part_d))
        return tuple(tiers)


def load_tax_law_dataset(path: str | Path = DEFAULT_TAX_LAW_JSON) -> TaxLawDataset:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Tax law dataset missing: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    values = tuple(TaxLawValue(**item) for item in data.get("values", []))
    brackets = tuple(TaxBracket(**item) for item in data.get("brackets", []))
    ds = TaxLawDataset(schema=str(data.get("schema", "tax_law_v10")), version=str(data.get("version", "v10")), generated_from=str(data.get("generated_from", "unknown")), values=values, brackets=brackets)
    if ds.schema != "tax_law_v10" or not ds.values or not ds.brackets:
        raise ValueError("Invalid or incomplete tax_law_v10 dataset")
    return ds


def dataset_freshness_summary(path: str | Path = DEFAULT_TAX_LAW_JSON) -> dict[str, Any]:
    ds = load_tax_law_dataset(path)
    latest = max(v.effective_year for v in ds.values)
    return {"schema": ds.schema, "version": ds.version, "value_count": len(ds.values), "bracket_count": len(ds.brackets), "latest_effective_year": latest, "source": ds.generated_from}
