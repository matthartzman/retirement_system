from datetime import date
from pathlib import Path


def test_load_actuals_creates_taxonomy_category_and_alias_for_unmapped_category(tmp_path):
    """Regression test for #251: load_actuals_payload() must promote transaction
    categories that have no taxonomy/alias mapping into new taxonomy categories
    (previously it iterated summary["tracking_types"], which is built entirely
    from already-mapped categories, so merged_count was always 0)."""
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    year = date.today().year
    txn_date = date(year, 1, 15).isoformat()
    (input_dir / "ytd_transactions.csv").write_text(
        "Date,Merchant,Category,Account,Amount,Owner,MappedCategoryId,Confirmed,Notes\n"
        f"{txn_date},Mystery Merchant,Mystery Category,Checking,-42.50,,,,\n",
        encoding="utf-8",
    )

    service = SpendingService(SpendingServiceContext(base_dir=tmp_path))
    payload, status = service.load_actuals_payload()

    assert status == 200
    assert payload["success"] is True
    assert payload["merged_count"] > 0
    assert any(m["category"] == "Mystery Category" for m in payload["merged"])

    from src import spending_tracker as st

    flat = st.taxonomy_flat(tmp_path)
    new_ids = [cid for cid, info in flat.items() if info.get("label") == "Mystery Category"]
    assert new_ids, "expected a new taxonomy category for the unmapped transaction category"
    new_id = new_ids[0]
    assert flat[new_id]["tracking_type"] == "Core Expenses"

    rules = st.load_mapping_rules(tmp_path)
    assert any(
        r.get("category_id") == new_id and r.get("keyword", "").lower() == "mystery category"
        for r in rules
    ), "expected an alias rule mapping the raw category text to the new taxonomy category"

    assert new_id in payload["actuals"]
