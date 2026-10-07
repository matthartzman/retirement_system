"""WP4.5: plan-side override tables (custom capital-market assumptions, correlations, real-loss
curves) are plan_rows sections the engine reads."""
from __future__ import annotations

import pytest

from src import data_io, optimization as opt, plan_overrides as po, real_loss_curves
from src.stores import PlanStore

CLASS = next(iter(opt._BASE_ASSET_CLASSES))
OTHER = list(opt._BASE_ASSET_CLASSES)[1]


@pytest.fixture
def store():
    with PlanStore.open() as s:
        yield s


@pytest.fixture(autouse=True)
def _reset_assumptions():
    yield
    opt.reset_capital_market_assumptions()


def test_rows_round_trip_through_the_plan_in_row_order(store):
    rows = po.validate_rows(po.CMA, [
        {"horizon_years": "30", "preset": "baseline", "asset_class": CLASS, "expected_return": "11.5%", "volatility": " 0.2 "},
        {"asset_class": OTHER, "expected_return": "0.05"}])
    assert po.replace_rows(store, po.CMA, rows) == 2
    view = store.sectioned_data()
    assert list(view["Custom Capital Market"]) == ["row_1", "row_2"]
    assert view["Custom Capital Market"]["row_1"]["volatility"] == "0.2"  # cells stripped
    assert po.override_rows(view, po.CMA) == [
        {"horizon_years": "30", "preset": "baseline", "asset_class": CLASS, "expected_return": "11.5%", "volatility": "0.2"},
        {"asset_class": OTHER, "expected_return": "0.05"}]
    # a second write replaces the table; an empty list clears it
    po.replace_rows(store, po.CMA, rows[:1])
    assert list(store.sectioned_data()["Custom Capital Market"]) == ["row_1"]
    po.replace_rows(store, po.CMA, [])
    assert "Custom Capital Market" not in store.sectioned_data() and po.override_rows(store.sectioned_data(), po.CMA) == []


def test_row_numbers_sort_numerically_not_as_text(store):
    for n in (10, 2, 1):
        store.insert_row(po.SECTIONS[po.REAL_LOSS], subsection=f"row_{n}", label="curve_name", value=f"c{n}")
        store.insert_row(po.SECTIONS[po.REAL_LOSS], subsection=f"row_{n}", label="holding_years", value=str(n))
        store.insert_row(po.SECTIONS[po.REAL_LOSS], subsection=f"row_{n}", label="real_loss_prob", value="10%")
    names = [r["curve_name"] for r in po.override_rows(store.sectioned_data(), po.REAL_LOSS)]
    assert names == ["c1", "c2", "c10"]


@pytest.mark.parametrize("kind, row, message", [
    (po.CMA, {"asset_class": "Nope", "expected_return": "5%"}, "not a known asset class"),
    (po.CMA, {"asset_class": CLASS, "expected_return": "five"}, "must be a number"),
    (po.CMA, {"asset_class": CLASS, "preset": "wild"}, "preset must be one of"),
    (po.CMA, {"expected_return": "5%"}, "asset_class is required"),
    (po.CMA, {"asset_class": CLASS, "colour": "red"}, "unknown column"),
    (po.CORRELATIONS, {"asset_class_a": CLASS, "asset_class_b": OTHER, "correlation": "1.5"}, "between -1 and 1"),
    (po.CORRELATIONS, {"asset_class_a": CLASS, "asset_class_b": OTHER}, "correlation"),
    (po.REAL_LOSS, {"curve_name": "x", "holding_years": "3", "real_loss_prob": "150%"}, "between 0 and 1"),
    (po.REAL_LOSS, {"holding_years": "3", "real_loss_prob": "10%"}, "curve_name is required"),
])
def test_invalid_rows_are_refused_with_every_problem_listed(kind, row, message):
    with pytest.raises(po.OverrideRowsError) as exc:
        po.validate_rows(kind, [row])
    assert message in "; ".join(exc.value.errors)


def test_validate_rows_needs_a_list():
    with pytest.raises(po.OverrideRowsError):
        po.validate_rows(po.CMA, {"rows": []})


def test_correlation_pairs_may_use_percent_and_negative_values():
    rows = po.validate_rows(po.CORRELATIONS, [{"asset_class_a": CLASS, "asset_class_b": OTHER, "correlation": "-0.25"},
                                               {"asset_class_a": OTHER, "asset_class_b": CLASS, "correlation": "30%"}])
    assert [r["correlation"] for r in rows] == ["-0.25", "30%"]


def _config(store, **globals_):
    store.set_value("Asset Class Assumptions", "Global", "capital_market_assumption_preset", "BASELINE")
    store.set_value("Asset Class Assumptions", "Global", "capital_market_assumption_horizon_years", "30")
    for key, value in globals_.items():
        store.set_value("Asset Class Assumptions", "Global", key, value)
    return data_io.parse_allocation_optimizer_inputs(store.sectioned_data())


def test_a_plan_without_override_rows_has_no_override_keys(store):
    c = _config(store)
    assert "custom_capital_market_rows" not in c["capital_market_config"]
    assert "custom_correlation_rows" not in c["capital_market_config"]
    assert "real_loss_curve_rows" not in c


def test_override_rows_reach_the_engine_config_and_apply_when_custom_is_selected(store):
    po.replace_rows(store, po.CMA, po.validate_rows(po.CMA, [
        {"horizon_years": "30", "preset": "BASELINE", "asset_class": CLASS, "expected_return": "11.5%", "volatility": "0.2"}]))
    po.replace_rows(store, po.CORRELATIONS, po.validate_rows(po.CORRELATIONS, [
        {"asset_class_a": CLASS, "asset_class_b": OTHER, "correlation": "0.42"}]))
    curve = next(iter(real_loss_curves.load_real_loss_curves()))  # a shipped curve
    po.replace_rows(store, po.REAL_LOSS, po.validate_rows(po.REAL_LOSS, [
        {"curve_name": curve, "holding_years": "5", "real_loss_prob": "60%"}]))
    # not selected: the rows are stored and carried, but the engine keeps the shipped table
    c = _config(store)
    assert len(c["capital_market_config"]["custom_capital_market_rows"]) == 1
    opt.apply_capital_market_config({"capital_market_config": c["capital_market_config"]})
    assert opt.ASSET_CLASSES[CLASS]["ret"] != 0.115
    # selected: the override wins over the shipped assumptions
    c = _config(store, use_custom_capital_market_file="YES", use_custom_correlations_file="YES")
    out = opt.apply_capital_market_config({"capital_market_config": c["capital_market_config"]})
    assert opt.ASSET_CLASSES[CLASS]["ret"] == 0.115 and opt.ASSET_CLASSES[CLASS]["vol"] == 0.2
    assert opt.ASSET_CLASSES[CLASS]["assumption_source"].endswith("custom_rows")
    assert opt.get_correlation(CLASS, OTHER) == pytest.approx(0.42)
    assert out["assumption_mode"] == "PRESET"
    # real-loss curves: the override replaces that curve for this plan only
    assert c["real_loss_curve_rows"] == [{"curve_name": curve, "holding_years": "5", "real_loss_prob": "60%"}]
    assert real_loss_curves.load_real_loss_curves(c)[curve] == [(5.0, 0.6)]
    assert real_loss_curves.load_real_loss_curves({})[curve] != [(5.0, 0.6)]
