"""#332 W-F Task F6 (design 2026-09-24 §9.1): within each answer-type
workbook section, sheets order by Topic (DOMAINS order) and then by the
existing letter_rank, so the tab strip shows both facets: answer type
(number) and Topic (sequence).
"""
from src import module_catalog as mc
from src.module_catalog import SHEET_REGISTRY
from src.reporting import workbook_common as w


class _WB:
    sheetnames = list(SHEET_REGISTRY)


def _final_order():
    r = w.compute_final_sheet_renames(_WB())
    return sorted({v for k, v in r.items() if k in SHEET_REGISTRY})


def test_sheets_within_a_section_follow_topic_order():
    rank = {d: i for i, d in enumerate(mc.DOMAINS)}
    inv = {v: k for k, v in w.compute_final_sheet_renames(_WB()).items() if k in SHEET_REGISTRY}
    by_section = {}
    for final in _final_order():
        by_section.setdefault(final[0], []).append(rank[w.sheet_topic(inv[final])])
    for sec, ranks in by_section.items():
        assert ranks == sorted(ranks), sec


def test_no_final_tab_name_carries_a_legacy_number():
    import re
    for final in _final_order():
        assert re.match(r"^[1-5][A-Z]{1,2}\. ", final), final
