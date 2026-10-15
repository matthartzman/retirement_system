from __future__ import annotations

"""Seed the Monarch account matches (and their policy) from a mapping CSV.

The CSV is the hand-made draft ``Monarch,App Location,App Field,Status,Primary Source``. Each row becomes a
saved match in ``monarch_account_map`` keyed by the Monarch account's normalized name. Rows whose target
exists today are saved with a real target; rows that point at things the page cannot write yet (Other Asset
Items rows, liabilities, notes, income streams) are saved with kind ``pending`` and ``ref`` =
``"<App Location>|<App Field>"`` so the intent is kept and a later phase resolves it.

Policy (see ``monarch_repo.POLICIES``): field ``IGNORE`` -> ignore; the SS/Pensions/Annuities location -> app
(the app is the source for those, by the user's decision); Primary Source Monarch -> auto; App -> app.
A blank App Location with a real field is treated as Other Assets and Liabilities (Costco Visa).
Closed accounts are not a policy: closedness is computed from the balances.
"""

import csv
import io
import re
import unicodedata
from pathlib import Path
from typing import Any

from . import active_plan
from . import ytd_tracking as ytd
from .reconcile import MAP_IGNORE, MAP_SETUP, PLAN_TARGETS

LOC_INVEST = "Investment Holdings"
LOC_OTHER = "Other Assets and Liabilities"
LOC_STREAMS = "SS, Pensions, & Annuities"
KIND_PENDING = "pending"

# CSV App Field -> plan-input target that exists today.
_PLAN_FIELDS = {"primary home - home value": "plan:home", "primary home - current loan amount": "plan:mortgage"}
assert set(_PLAN_FIELDS.values()) <= set(PLAN_TARGETS)


def account_key(name: str) -> str:
    """Same identity key the Monarch extractor writes (NFKC, collapsed whitespace, case-folded)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name or "")).strip().casefold()


def parse_mapping_csv(text: str) -> list[dict[str, str]]:
    rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff")))]
    return [r for r in rows if r.get("Monarch")]


def read_mapping_csv(path: str | Path) -> list[dict[str, str]]:
    return parse_mapping_csv(Path(path).read_text(encoding="utf-8-sig"))


def policy_for(row: dict[str, str]) -> str:
    if row.get("App Field", "").upper() == "IGNORE":
        return "ignore"
    if row.get("App Location") == LOC_STREAMS:
        return "app"
    return "auto" if row.get("Primary Source", "").casefold() == "monarch" else "app"


def seed_mapping(base_dir: str | Path, csv_path: str | Path | None = None, *, dry_run: bool = False,
                 csv_text: str | None = None) -> dict[str, Any]:
    """Save the CSV's matches. Returns ``{saved, pending, ignored, not_in_monarch, skipped}`` lists of
    ``{monarch, ...}``; ``not_in_monarch`` rows (no stored balances under that name) are never saved."""
    base = Path(base_dir)
    rows = parse_mapping_csv(csv_text) if csv_text is not None else read_mapping_csv(csv_path)
    report: dict[str, list[dict[str, str]]] = {k: [] for k in ("saved", "pending", "ignored", "not_in_monarch", "skipped")}
    with active_plan.workspace_store(base, write=not dry_run) as store:
        known = {a["account_key"] for a in store.monarch.accounts_as_of(store.monarch.latest_date() or "9999-12-31")}
        setup = {str(r.get("Account") or "").strip().casefold(): str(r.get("Account") or "").strip()
                 for r in store.dataset("ytd_account_setup").rows()}
        for r in rows:
            key = account_key(r["Monarch"])
            field, loc = r.get("App Field", ""), r.get("App Location", "")
            item = {"monarch": r["Monarch"], "field": field, "location": loc}
            if key not in known:
                report["not_in_monarch"].append(item)
                continue
            policy = policy_for(r)
            if field.upper() == "IGNORE":
                kind, ref, bucket = MAP_IGNORE, "", "ignored"
            elif not field:
                report["skipped"].append(item)
                continue
            else:
                loc = loc or LOC_OTHER
                if field.casefold() in _PLAN_FIELDS:
                    kind, ref, bucket = _PLAN_FIELDS[field.casefold()], "", "saved"
                elif loc in (LOC_INVEST, LOC_OTHER) and field.casefold() in setup:
                    kind, ref, bucket = MAP_SETUP, setup[field.casefold()], "saved"
                else:
                    kind, ref, bucket = KIND_PENDING, f"{loc}|{field}", "pending"
            report[bucket].append({**item, "kind": kind, "policy": policy})
            if not dry_run:
                store.monarch.set_mapping(key, kind, ref, policy)
    return report
