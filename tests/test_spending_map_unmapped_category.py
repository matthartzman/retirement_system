"""'Map to category' on the unmapped-categories warning: existing category or
new category + exact category alias, case-insensitive, rolls into the group."""
from datetime import date

from src.server_services.spending_service import SpendingService, SpendingServiceContext
from tests.plan_fixture import write_plan_dataset


def _service(tmp_path, cat="Mystery Category"):
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    d = date(date.today().year, 1, 15).isoformat()
    write_plan_dataset(
        tmp_path, "ytd_transactions.csv",
        "Date,Merchant,Category,Account,Amount,Owner,MappedCategoryId,Confirmed,Notes\n"
        f"{d},Shop,{cat},Checking,-42.50,,,,\n",
    )
    return SpendingService(SpendingServiceContext(base_dir=tmp_path))


def _unmapped(svc):
    payload, status = svc.dashboard_payload()
    assert status == 200
    return payload["unmapped_categories"], payload


def test_new_category_plus_alias_clears_warning_and_rolls_into_group(tmp_path):
    svc = _service(tmp_path)
    assert _unmapped(svc)[0] == ["Mystery Category"]
    out, status = svc.category_create_payload({
        "label": "Mystery Category", "tracking_type": "Core Expenses",
        "group": "Brand New Group", "match_value": "Mystery Category",
        "match_field": "category", "exact": True,
    })
    assert status == 200 and out["success"]
    unmapped, payload = _unmapped(svc)
    assert unmapped == []
    assert "Brand New Group" in str(payload)


def test_existing_category_alias_only_and_case_insensitive(tmp_path):
    svc = _service(tmp_path, cat="MYSTERY category")
    created, _ = svc.category_create_payload({"label": "Hobbies", "tracking_type": "Core Expenses", "group": "Fun"})
    out, status = svc.alias_add_payload({
        "match_value": "MYSTERY category", "category_id": created["id"],
        "match_field": "category", "exact": True,
    })
    assert status == 200 and out["success"]
    assert _unmapped(svc)[0] == []
    from src import spending_tracker as st
    assert "mystery category" in st.load_category_map(tmp_path)


def test_alias_unknown_category_rejected(tmp_path):
    svc = _service(tmp_path)
    out, status = svc.alias_add_payload({"match_value": "x", "category_id": "nope"})
    assert status == 400 and not out["success"]
