"""Left-nav Features popover: every switchable catalog feature must have a host page.

frontend/js/dashboard_decomp_nav_features.js lists each optional module and plan flag under the nav group of the
page where its inputs appear (FEATURE_HOST). A catalog feature missing from that map would silently vanish from
every popover, so this test fails until it is assigned.
"""
import re
from pathlib import Path

from src.module_catalog import CATALOG
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "frontend" / "js" / "dashboard_decomp_nav_features.js").read_text(encoding="utf-8")
DASH = dashboard_js_text()


def _host_map():
    body = re.search(r"export const FEATURE_HOST = \{(.*?)\n\};", SRC, re.S).group(1)
    return dict(re.findall(r'^\s{2}([a-z0-9_]+): \[(.*?)\],', body, re.M))


def _step_ids():
    block = DASH[DASH.index("const STEPS = ["):]
    block = block[: block.index("\n];")]
    return set(re.findall(r'\n    id: "(\w+)"', block))


def test_every_switchable_catalog_feature_has_a_host_page():
    hosts = _host_map()
    switchable = {k for k, m in CATALOG.items() if m.optional or m.gate_kind == "plan_flag"}
    assert sorted(switchable - set(hosts)) == [], "catalog features with no FEATURE_HOST entry"
    assert sorted(set(hosts) - switchable) == [], "FEATURE_HOST entries that are not switchable catalog features"


def test_host_pages_are_real_nav_steps_or_a_group_override():
    steps = _step_ids()
    for key, spec in _host_map().items():
        first = spec.split(",")[0].strip()
        if first == "null":
            assert spec.count('"') >= 4, f"{key}: a workbook-only feature needs a group override"
        else:
            assert first.strip('"') in steps, f"{key}: host step {first} is not a STEPS entry"
