import json
from pathlib import Path

from src.results_model import RESULTS_MODEL_SCHEMA, build_result_explorer_model, model_index, model_sheet


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "results_model_v10_contract.json"


def _contract_model():
    config = {
        "h_name": "Matt",
        "w_name": "Pat",
        "plan_start": 2026,
        "plan_end": 2027,
        "state": "IL",
        "asset_targets": {"US Stocks": 0.55, "Bonds": 0.35, "Cash": 0.10},
    }
    rows = [
        {
            "year": 2026,
            "h_age": 50,
            "w_age": 49,
            "earned": 100000,
            "spend_base_yr": 80000,
            "rec_extra": 5000,
            "mortgage": 36000,
            "fed_tax": 10000,
            "state_tax": 3000,
            "total_tax": 13000,
            "agi": 100000,
            "taxable_inc": 90000,
            "roth_conv": 12000,
            "total_nw": 1000000,
            "pretax_nw": 100000,
            "roth_nw": 50000,
            "trust_nw": 25000,
            "hsa_nw": 10000,
            "home_equity": 500000,
            "other_nw": 50000,
            "surplus": -29000,
        },
        {
            "year": 2027,
            "h_age": 51,
            "w_age": 50,
            "earned": 90000,
            "spend_base_yr": 83000,
            "rec_extra": 4000,
            "mortgage": 36000,
            "fed_tax": 9500,
            "state_tax": 3000,
            "total_tax": 12500,
            "agi": 95000,
            "taxable_inc": 88000,
            "roth_conv": 10000,
            "total_nw": 1050000,
            "pretax_nw": 110000,
            "roth_nw": 60000,
            "trust_nw": 30000,
            "hsa_nw": 11000,
            "home_equity": 510000,
            "other_nw": 52000,
            "surplus": -31500,
        },
    ]
    return build_result_explorer_model(config, rows, {"success_rate": 0.98})


def _cell_kinds(model):
    kinds = set()
    for page in model.get("sheets") or []:
        for section in page.get("sections") or []:
            for row in section.get("rows") or []:
                for cell in row.get("cells") or []:
                    kinds.add(cell.get("kind"))
    return kinds


def test_results_model_v10_matches_contract_fixture():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    model = _contract_model()

    assert model["schema"] == expected["schema"] == RESULTS_MODEL_SCHEMA
    assert model["source"] == expected["source"]
    assert model["version"] == expected["version"]
    assert model["sheet_count"] == expected["sheet_count"]
    assert [c["name"] for c in model["categories"]] == expected["category_names"]

    pages = {page["name"]: page for page in model["sheets"]}
    assert list(pages) == [item["name"] for item in expected["sheets"]]
    for sheet_spec in expected["sheets"]:
        page = pages[sheet_spec["name"]]
        assert page["kind"] == sheet_spec["kind"]
        assert page["category"] == sheet_spec["category"]
        if page["kind"] == "chart_dashboard":
            assert page["chart_count"] == sheet_spec["chart_count"]
            chart_titles = [chart["title"] for chart in page["charts"]]
            for title, prefix in zip(chart_titles, sheet_spec["chart_title_prefixes"]):
                assert title.startswith(prefix)
        else:
            assert page["section_count"] == sheet_spec["section_count"]
            assert page["row_count"] >= sheet_spec["min_row_count"]

    assert set(expected["required_cell_kinds"]).issubset(_cell_kinds(model))


def test_results_model_index_and_sheet_helpers_preserve_semantic_contract():
    model = _contract_model()

    index = model_index(model)
    assert index["schema"] == "results_model_v10"
    assert index["mode"] == "index"
    assert len(index["sheets"]) == model["sheet_count"]
    assert all(sheet["source"] == "semantic_results_model" for sheet in index["sheets"])

    charts = model_sheet(model, "1E. Charts")
    assert charts is not None
    assert charts["success"] is True
    assert charts["kind"] == "chart_dashboard"
    assert charts["source"] == "semantic_results_model"
