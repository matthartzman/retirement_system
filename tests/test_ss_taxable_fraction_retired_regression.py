"""WI-028 / FIN-008: the Social Security taxable-fraction lever is retired.

The engine always computed the statutory IRC 86 share, so the stored override
never affected tax. The lever, its summary row and the stored rows are gone.
"""
from src import tax_assumptions as ta
from src.plan_data_migration import migrate_rows, migrate_sectioned_data

KEY = "social_security_taxable_fraction"


def test_lever_is_not_registered():
    assert KEY not in ta.LEVER_BY_KEY
    assert all(lv.engine_key != "ss_taxable" for lv in ta.LEVERS)


def test_migration_drops_stored_row():
    rows = [["Economic Assumptions", "", KEY, "85.00%", "pct", "", ""],
            ["Economic Assumptions", "", "portfolio_nominal_return", "6%", "pct", "", ""]]
    out, changed = migrate_rows(rows)
    assert changed == 1
    assert [r[2] for r in out] == ["portfolio_nominal_return"]


def test_migration_drops_key_from_sectioned_data():
    data = {"Economic Assumptions": {"": {KEY: "0.5", "inflation_general": "2%"}}}
    out, changed = migrate_sectioned_data(data)
    assert changed == 1
    assert out["Economic Assumptions"][""] == {"inflation_general": "2%"}
