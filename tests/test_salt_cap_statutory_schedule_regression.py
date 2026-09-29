"""WI-302 / FIN-005: the SALT-cap schedule, its reversion year and the CA
bracket vintage are keyed by absolute statutory year, not by the calendar year
the app runs in (TAX_REFERENCE_YEAR, which defaults to today's year).

Each reference year is exercised in a fresh interpreter because src/taxes.py
reads TAX_REFERENCE_YEAR once at import time.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_PROBE = r"""
import json
from src import core, taxes
out = {
    'caps': {y: core.salt_cap(y, 0) for y in range(2024, 2034)},
    'cap_2026_mfs': core.salt_cap(2026, 0, 'MFS'),
    'cap_2027_high_magi': core.salt_cap(2027, 700000),
    'reversion': taxes.SALT_REVERSION_YEAR,
    'ca_tax_2030': core.state_income_tax('California', 0.0, 0.0, 0.0, 300000.0, 0.0, 0.0, 2030, True, 'MFJ', 0.02),
    'ny_tax_2030': core.state_income_tax('New York', 0.0, 0.0, 0.0, 300000.0, 0.0, 0.0, 2030, True, 'MFJ', 0.02),
}
print(json.dumps(out))
"""


def _probe(reference_year: str) -> dict:
    env = dict(os.environ)
    env["TAX_REFERENCE_YEAR"] = reference_year
    env.pop("RETIREMENT_TAX_YEAR", None)
    res = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def probes():
    return {yr: _probe(yr) for yr in ("2026", "2027", "2028")}


@pytest.mark.parametrize("ref", ["2026", "2027", "2028"])
def test_salt_cap_schedule_is_absolute_statutory_years(probes, ref):
    caps = {int(k): v for k, v in probes[ref]["caps"].items()}
    assert caps[2024] == 10000
    assert caps[2025] == 40000
    assert caps[2026] == 40400
    assert caps[2027] == 40804
    assert caps[2028] == 41212
    assert caps[2029] == 41624
    assert caps[2030] == 10000
    assert caps[2033] == 10000
    assert probes[ref]["reversion"] == 2030


def test_salt_results_do_not_depend_on_reference_year(probes):
    first = probes["2026"]
    for ref in ("2027", "2028"):
        assert probes[ref] == first


def test_mfs_gets_half_the_cap(probes):
    assert probes["2026"]["cap_2026_mfs"] == 20200


def test_phasedown_uses_threshold_grown_one_percent_a_year(probes):
    # 2027 threshold = 500,000 * 1.01**2 = 510,050; cap 40,804 - 30% of excess, floored at 10,000.
    expected = max(40804 - 0.30 * (700000 - 500000 * 1.01 ** 2), 10000)
    assert probes["2026"]["cap_2027_high_magi"] == pytest.approx(expected)


def test_state_brackets_do_not_shift_with_reference_year(probes):
    for ref in ("2027", "2028"):
        assert probes[ref]["ca_tax_2030"] == pytest.approx(probes["2026"]["ca_tax_2030"])
        assert probes[ref]["ny_tax_2030"] == pytest.approx(probes["2026"]["ny_tax_2030"])


def test_ca_brackets_tagged_with_their_2024_value_year():
    from src.core import _STATE_INCOME_BRACKETS_VALUE_YEARS
    assert _STATE_INCOME_BRACKETS_VALUE_YEARS["California"] == 2024


def test_dataset_salt_rows_do_not_overlap():
    data = json.loads((ROOT / "reference_data" / "tax_law_v10.json").read_text(encoding="utf-8"))
    rows = sorted((v["effective_year"], v.get("expires_year")) for v in data["values"] if v["name"] == "salt_cap")
    for (eff_a, exp_a), (eff_b, _exp_b) in zip(rows, rows[1:]):
        assert exp_a is not None and exp_a < eff_b, rows


def test_orphan_config_salt_cap_is_gone():
    src = (ROOT / "src" / "data_io.py").read_text(encoding="utf-8")
    assert "c['salt_cap']" not in src
