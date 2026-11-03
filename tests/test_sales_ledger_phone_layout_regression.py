"""Sales Ledger page at phone width: its panels sit in a ``.field-list`` grid whose single column must be allowed to
shrink (``min-width: 0``), otherwise the wide queue / 1099-B tables push the panels past the card and clip on a phone
(seen in a real browser at 390px: the bulk-review panel measured 508px inside a 344px page)."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "frontend" / "css" / "dashboard.css"


def test_field_list_children_may_shrink_below_their_content_width():
    rule = re.search(r"\.field-list>\*\{([^}]*)\}", CSS.read_text(encoding="utf-8"))
    assert rule, ".field-list>* rule missing"
    assert "min-width:0" in rule.group(1).replace(" ", "")
