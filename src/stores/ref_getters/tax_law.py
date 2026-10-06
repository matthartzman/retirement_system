"""Federal tax-law dataset from ``reference.db`` (WP3.2).

Tables ``tax_law_meta`` / ``tax_law_value`` / ``tax_law_bracket`` (built by
``tools/reference_slices/tax_law.py``). ``tax_law_dataset`` returns the same frozen
``TaxLawDataset`` the old ``tax_law_v10.json`` loader built: values and brackets in
file order, int/float preserved, absent ``expires_year`` / open ``upper`` as ``None``.
"""
from __future__ import annotations

from typing import Any

from ..ref_access import reference
from ..ref_data import RefData

_VALUE_COLS = ("jurisdiction", "filing_status", "name", "value", "effective_year", "expires_year", "source", "status")
_BRACKET_COLS = ("jurisdiction", "filing_status", "bracket_type", "lower", "upper", "rate", "effective_year",
                 "expires_year", "source", "status")


def tax_law_dataset(ref: RefData | None = None):
    """A ``TaxLawDataset`` (frozen, built fresh); raises ``ValueError`` if incomplete."""
    from ...tax_law import TaxBracket, TaxLawDataset, TaxLawValue
    ref = reference() if ref is None else ref
    meta = ref.query('SELECT "schema", "version", "generated_from" FROM "tax_law_meta"')
    values = tuple(TaxLawValue(**{c: r[c] for c in _VALUE_COLS}) for r in ref.query(
        f'SELECT {", ".join(_VALUE_COLS)} FROM "tax_law_value" ORDER BY seq'))
    brackets = tuple(TaxBracket(**{c: r[c] for c in _BRACKET_COLS}) for r in ref.query(
        f'SELECT {", ".join(_BRACKET_COLS)} FROM "tax_law_bracket" ORDER BY seq'))
    m = meta[0] if meta else {"schema": "tax_law_v10", "version": "v10", "generated_from": "unknown"}
    ds = TaxLawDataset(schema=m["schema"], version=m["version"], generated_from=m["generated_from"],
                       values=values, brackets=brackets)
    if ds.schema != "tax_law_v10" or not ds.values or not ds.brackets:
        raise ValueError("Invalid or incomplete tax_law_v10 dataset")
    return ds


def tax_law_freshness(ref: RefData | None = None) -> dict[str, Any]:
    ds = tax_law_dataset(ref)
    latest = max(v.effective_year for v in ds.values)
    return {"schema": ds.schema, "version": ds.version, "value_count": len(ds.values),
            "bracket_count": len(ds.brackets), "latest_effective_year": latest, "source": ds.generated_from}
