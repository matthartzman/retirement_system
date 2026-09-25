"""#332 W-F Task F4 (design 2026-09-24 §1.4): the cross-surface consistency
guard. A nav group label is either a Topic label, a legal '&'-join of Topic
labels, or in the explicit utility allowlist; answer-type labels equal the
workbook's five section titles; and no nav group reuses a Topic label for a
different module membership. This test PASSES once every earlier W-F task
(nav regroup, Household/Income & Benefits split) lands correctly -- a
failure here means fix the surface (nav grouping), never this test.
"""
import re

from src import module_catalog as mc
from src.reporting.workbook_common import _SECTION_META
from tests._decomp_dashboard import dashboard_js_text

UTILITY = {"Plan Status", "Household", "Strategy", "Reports & Review", "Settings"}


def _nav_groups():
    src = dashboard_js_text()
    steps_block = re.search(r"const STEPS = \[(.*?)\n\];", src, re.S).group(1)
    return list(dict.fromkeys(re.findall(r'group:\s*"([^"]+)"', steps_block)))


def _is_join(label):
    parts = [p.strip() for p in label.split("&")]
    topics_words = {w for d in mc.DOMAINS for w in (p.strip() for p in d.split("&"))}
    return all(p in topics_words for p in parts)


def test_every_nav_group_is_topic_join_or_utility():
    for g in _nav_groups():
        assert g in mc.DOMAINS or g in UTILITY or _is_join(g), g


def test_answer_type_labels_equal_workbook_sections():
    titles = [_SECTION_META[str(i)][0].split(". ", 1)[1] for i in range(1, 6)]
    assert titles == list(mc.ANSWER_TYPES)


def test_topic_label_never_reused_for_other_membership():
    # A nav group named exactly like a topic may only hold steps owned by
    # modules of that topic.
    src = dashboard_js_text()
    for m in mc.CATALOG.values():
        if m.dashboard_step:
            hit = re.search(r'id:\s*"%s",\s*group:\s*"([^"]+)"' % re.escape(m.dashboard_step), src)
            if hit and hit.group(1) in mc.DOMAINS:
                assert hit.group(1) == m.domain, (m.dashboard_step, hit.group(1), m.domain)
