from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_user_field_helper_no_longer_uses_label_equals_value_boilerplate():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    forbidden = [
        "value the planner should use for this household",
        "is the ${friendlyGroup(row).toLowerCase()} value",
        "is the ",
    ]
    assert "fieldDefaultMeaning" in js
    assert "Records the actual birth date used to calculate age-based rules" in js
    assert "Describes a cash inflow the household expects to receive" in js
    assert "Describes a cash outflow the plan must fund" in js
    assert "Quantifies or classifies an asset, account, holding, or basis item" in js
    for phrase in forbidden[:2]:
        assert phrase not in js


def test_admin_setting_helper_has_meaningful_default_definitions():
    js = (ROOT / "frontend/js/admin.js").read_text(encoding="utf-8")
    assert "adminDefaultMeaning" in js
    assert "Controls how market values are obtained or reused" in js
    assert "Identifies a local file or adapter location" in js
    assert "Defines the value the next build" not in js
