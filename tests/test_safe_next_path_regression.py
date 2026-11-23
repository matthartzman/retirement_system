"""X-10: `safe_next_path` refuses every form a browser turns into a protocol-relative URL."""
from __future__ import annotations

import pytest

from src.server_services.base_service import safe_next_path


@pytest.mark.parametrize("raw", ["/\\evil.example", "/%5Cevil.example", "/%5cevil.example", "//evil.example", "/%09/evil.example",
                                 "/%0a/evil.example", "/\t/evil.example", "https://evil.example", "evil.example", "/%2F%2Fevil.example/",
                                 "\\\\evil.example", "/a\\b"])
def test_hostile_targets_fall_back_to_root(raw):
    assert safe_next_path(raw) == "/"


@pytest.mark.parametrize("raw", ["/", "/plan", "/plan?step=income#top", "/api/status"])
def test_ordinary_targets_pass(raw):
    assert safe_next_path(raw) == raw
