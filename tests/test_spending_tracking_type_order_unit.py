def test_wellness_and_housing_sort_last_in_tracking_type_order():
    from src.spending_tracker import TRACKING_TYPE_ORDER

    assert TRACKING_TYPE_ORDER == [
        "Income", "Core Expenses", "Travel", "Large Discretionary", "Business",
        "Wellness", "Housing",
    ]
    # Both moved to the tail, in the same relative order they were in before.
    assert TRACKING_TYPE_ORDER.index("Wellness") == len(TRACKING_TYPE_ORDER) - 2
    assert TRACKING_TYPE_ORDER.index("Housing") == len(TRACKING_TYPE_ORDER) - 1
