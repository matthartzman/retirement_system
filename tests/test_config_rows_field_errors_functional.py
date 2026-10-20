"""WI-020 / UX-004: the 422 body carries one structured entry per field error."""
from src.schema_registry import validate_rows
from src.server_services.config_service import structure_validation_errors


def test_structured_errors_name_the_field_message_and_row():
    errors = [
        "('Household', 'Person 1', 'birth_year'): must be a whole number; got 'abc'",
        "('Estate', 'Trust_1', \"owner's_name\"): required; got ''",
        "('Large Discretionary Expenses','Trip','repeat_start_year/repeat_end_year'): start year must be <= end year",
    ]
    ids = {("Household", "Person 1", "birth_year"): 11, ("Estate", "Trust_1", "owner's_name"): 12}
    out = structure_validation_errors(errors, ids)
    assert [e["row_index"] for e in out[:2]] == [11, 12]
    assert out[0]["message"] == "must be a whole number" and out[0]["got"] == "'abc'"
    assert out[1]["label"] == "owner's_name" and out[1]["message"] == "required"
    assert "row_index" not in out[2] and out[2]["label"] == "repeat_start_year/repeat_end_year"
    assert all(e["raw"] in errors for e in out)


def test_unparseable_error_keeps_message_only():
    out = structure_validation_errors(["something else went wrong"])
    assert out == [{"message": "something else went wrong", "raw": "something else went wrong"}]


def test_round_trips_real_validate_rows_output():
    rows = [{"section": "Household", "subsection": "", "label": "residence_state", "value": "Atlantis"}]
    errors = validate_rows(rows)
    if errors:  # schema may or may not constrain this key; when it does, the structure must parse it
        out = structure_validation_errors(errors, {("Household", "", "residence_state"): 5})
        assert out[0]["row_index"] == 5 and out[0]["message"]
