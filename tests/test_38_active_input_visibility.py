from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dashboard_has_shared_active_input_usage_layer_and_page_summary():
    js = read("frontend/js/dashboard.js")
    assert "function rowBuildUsageState" in js
    assert "function inactiveValuesPanel" in js
    assert "function inactiveRowsForStep" in js
    assert 'content += inactiveValuesPanel(activeStep)' in js
    assert "Inactive values" in js
    assert "Why inactive" in js
    assert "What would activate it" in js
    assert "Likely effect on impacts" in js


def test_social_security_pia_and_claim_age_inputs_are_mutually_explained():
    js = read("frontend/js/dashboard.js")
    # The general "Inactive values" summary (elsewhere on the page) still
    # explains why a saved-but-unused FRA/PIA value isn't driving the build.
    assert "Monthly at FRA/PIA is blank or zero" in js
    assert (
        "the build uses the age-67 (Full Retirement Age) entry from this person's benefit table instead"
        in js
    )
    assert "function ssActiveCell" in js
    # But the Social Security compact table itself always renders Claim Age,
    # Monthly at FRA, and FRA Age as live editable inputs rather than
    # blocking them behind an inactive placeholder, so a user can enter FRA
    # values directly to derive the benefit at any claim age.
    assert "Inactive — listed above" not in js
    assert "fra_age" in js


def test_allocation_optimizer_hides_unused_user_targets_and_lists_them_inactive():
    js = read("frontend/js/dashboard.js")
    assert "User target percentages are hidden because the next build will not use them" in js
    assert "Allocation optimizer recommendation mode is selected" in js
    assert "Choose Use user-specified allocation" in js
    optimizer_header = "<th>Selection</th><th>Computed Optimizer Target %</th><th>Active Target Used %</th>"
    assert optimizer_header in js


def test_conditional_modules_and_modes_have_activation_explanations():
    js = read("frontend/js/dashboard.js")
    for token in [
        "Core spending is set to CPI/general inflation mode",
        "Monte Carlo is set to Simple / Quick Vectorized mode",
        "No home sale year is active",
        "HSA withdrawal mode is not annual percentage",
        "Roth Conversion Policy is set to no voluntary conversions",
        "Divorce/QDRO optional workbook module is turned off",
    ]:
        assert token in js


def test_inactive_values_styles_exist():
    css = read("frontend/css/dashboard.css")
    assert ".inactive-values-panel" in css
    assert ".inactive-cell" in css
    assert ".field.inactive-edit" in css
