from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")


def test_core_spending_renderer_is_flat_ordered_and_excludes_daf():
    js = _js()
    start = js.index("function renderSpendingCore()")
    end = js.index("function renderFields", start)
    body = js[start:end]
    assert "core-spending-flat" in body
    assert "renderFieldGroups(ordered)" not in body
    assert "daf_annual_contribution" not in body.split("const labels =", 1)[1].split("const ordered = [];", 1)[0]
    assert "DAF contributions" in body


def test_core_spending_route_excludes_daf_annual_contribution():
    js = _js()
    # Item 174 also excludes the legacy single Core-Spending base input.
    route = 'case "spending_core":\n        return (\n          (sec === "Cashflow" &&\n            sub === "spending" &&\n            lbl !== "daf_annual_contribution" &&\n            lbl !== "annual_spending_base_year")'
    assert route in js


def test_core_spending_control_order_in_renderer():
    js = _js()
    start = js.index("function renderSpendingCore()")
    end = js.index("function renderFields", start)
    body = js[start:end]
    labels_region = body.split("const labels =", 1)[1].split("const ordered = [];", 1)[0]
    manual_branch, cpi_branch = labels_region.split('mode === "manual_override"', 1)[1].split("? [", 1)[1].split(
        "]\n      : [", 1
    )
    cpi_branch = cpi_branch.split("];", 1)[0]
    order = [
        "core_spending_growth_mode",
        "annual_spending_base_year",
        "spending_freeze_year",
        "inflation_general",
    ]
    pos = [cpi_branch.index(f'"{x}"') for x in order]
    assert pos == sorted(pos)
    manual_order = [
        "core_spending_growth_mode",
        "annual_spending_base_year",
        "spending_freeze_year",
        "core_spending_manual_growth_rate",
    ]
    # Use the manual label list specifically so CPI branch does not satisfy this by accident.
    manual_pos = [manual_branch.index(f'"{x}"') for x in manual_order]
    assert manual_pos == sorted(manual_pos)


