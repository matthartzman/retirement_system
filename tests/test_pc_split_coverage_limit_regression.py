import pytest
import src.data_io  # noqa: F401  (load order: data_io first)
from src.parsing.advanced_modules import _coverage_limit


@pytest.mark.parametrize("raw,expected", [
    ("250/500", 500000.0),
    ("250/500/100", 500000.0),
    ("1,000,000", 1000000.0),
    ("$2000000", 2000000.0),
    ("0", 0.0),
])
def test_coverage_limit_split_and_plain(raw, expected, caplog):
    assert _coverage_limit(raw) == expected
    assert "unparseable" not in caplog.text
