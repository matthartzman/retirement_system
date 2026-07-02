"""Unit tests for src/security.py.

Covers every public function in the security module: secret redaction,
regex text redaction, SHA-256 fingerprinting, server-token lookup,
constant-time token comparison, audit-event appending, and bearer/header
extraction. Tests assert the module's ACTUAL current behavior (see the
module-level notes below for a couple of documented regex quirks).
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

import src.security as security


# ---------------------------------------------------------------------------
# redact_secret
# ---------------------------------------------------------------------------

def test_redact_secret_empty_string_returns_empty():
    assert security.redact_secret("") == ""


def test_redact_secret_none_returns_empty():
    assert security.redact_secret(None) == ""


def test_redact_secret_short_value_returns_stars():
    assert security.redact_secret("abc") == "***"


def test_redact_secret_boundary_exactly_8_chars_returns_stars():
    assert security.redact_secret("a" * 8) == "***"


def test_redact_secret_boundary_9_chars_masks_middle():
    # 9 chars is the first length that reveals first/last two.
    assert security.redact_secret("abcdefghi") == "ab***hi"


def test_redact_secret_long_value_masks_middle():
    assert security.redact_secret("sk-1234567890") == "sk***90"


def test_redact_secret_non_string_input_coerced():
    # An int is coerced via str(); 123456789 is 9 chars long.
    assert security.redact_secret(123456789) == "12***89"


def test_redact_secret_zero_int_is_truthy_string_but_falsy_value():
    # int 0 is falsy so str(value or "") -> "" -> returns "".
    assert security.redact_secret(0) == ""


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------

def test_redact_text_json_style_api_key():
    text = '{"api_key": "sk-abc123", "keep": 1}'
    out = security.redact_text(text)
    assert '"api_key": ***' in out
    assert "sk-abc123" not in out
    # Non-secret field is preserved.
    assert '"keep": 1' in out


def test_redact_text_query_string_apikey():
    out = security.redact_text("apikey=abc123&other=1")
    assert out == "apikey=***&other=1"
    assert "abc123" not in out


def test_redact_text_mixed_case_token():
    out = security.redact_text("Token: xyz")
    assert out == "Token: ***"


def test_redact_text_password_key():
    assert security.redact_text("password=hunter2") == "password=***"


def test_redact_text_no_secret_passthrough_unchanged():
    text = "The quarterly report shows steady growth across all funds."
    assert security.redact_text(text) == text


def test_redact_text_word_secret_without_kv_shape_not_redacted():
    # "secret" appears but without a following [:=]value, so no redaction.
    text = "this is a secret message that should remain visible"
    assert security.redact_text(text) == text


def test_redact_text_secret_with_kv_shape_is_redacted():
    # Confirms the flip side: a real key:value shape DOES redact.
    out = security.redact_text("the secret: hunter2 here")
    assert out == "the secret: *** here"


def test_redact_text_none_returns_empty_string():
    assert security.redact_text(None) == ""


def test_redact_text_quoted_and_unquoted_keys_both_match():
    assert security.redact_text('"password": "p@ss"') == '"password": ***'
    assert security.redact_text("token=raw") == "token=***"


# ---------------------------------------------------------------------------
# sha256_fingerprint
# ---------------------------------------------------------------------------

def test_sha256_fingerprint_deterministic():
    assert security.sha256_fingerprint("hello") == security.sha256_fingerprint("hello")


def test_sha256_fingerprint_length_is_12():
    assert len(security.sha256_fingerprint("hello")) == 12


def test_sha256_fingerprint_is_hex():
    fp = security.sha256_fingerprint("hello")
    int(fp, 16)  # raises ValueError if not valid hex


def test_sha256_fingerprint_different_inputs_differ():
    assert security.sha256_fingerprint("a") != security.sha256_fingerprint("b")


def test_sha256_fingerprint_empty_returns_empty():
    assert security.sha256_fingerprint("") == ""


def test_sha256_fingerprint_none_returns_empty():
    assert security.sha256_fingerprint(None) == ""


def test_sha256_fingerprint_known_value():
    import hashlib
    expected = hashlib.sha256(b"hello").hexdigest()[:12]
    assert security.sha256_fingerprint("hello") == expected


# ---------------------------------------------------------------------------
# get_server_token
# ---------------------------------------------------------------------------

class _FakeConfig:
    def __init__(self, token):
        self.server_api_token = token


def test_get_server_token_real_token_stripped():
    with mock.patch("src.runtime_config.load_runtime_config",
                    return_value=_FakeConfig("  my-token  ")):
        assert security.get_server_token() == "my-token"


def test_get_server_token_whitespace_only_returns_none():
    with mock.patch("src.runtime_config.load_runtime_config",
                    return_value=_FakeConfig("   ")):
        assert security.get_server_token() is None


def test_get_server_token_empty_returns_none():
    with mock.patch("src.runtime_config.load_runtime_config",
                    return_value=_FakeConfig("")):
        assert security.get_server_token() is None


def test_get_server_token_none_attr_returns_none():
    with mock.patch("src.runtime_config.load_runtime_config",
                    return_value=_FakeConfig(None)):
        assert security.get_server_token() is None


# ---------------------------------------------------------------------------
# constant_time_token_ok
# ---------------------------------------------------------------------------

def test_constant_time_token_ok_exact_match():
    assert security.constant_time_token_ok("secret", "secret") is True


def test_constant_time_token_ok_mismatch():
    assert security.constant_time_token_ok("wrong", "secret") is False


def test_constant_time_token_ok_expected_none_returns_false():
    assert security.constant_time_token_ok("anything", None) is False


def test_constant_time_token_ok_expected_empty_returns_false():
    assert security.constant_time_token_ok("anything", "") is False


def test_constant_time_token_ok_candidate_none_does_not_raise():
    # None candidate is coerced to "" and compared against a real expected.
    assert security.constant_time_token_ok(None, "secret") is False


def test_constant_time_token_ok_candidate_none_expected_none():
    assert security.constant_time_token_ok(None, None) is False


# ---------------------------------------------------------------------------
# append_audit_event
# ---------------------------------------------------------------------------

def _read_audit_lines(base_dir):
    log_path = base_dir / "output" / "audit_log.jsonl"
    return log_path.read_text(encoding="utf-8").splitlines()


def test_append_audit_event_creates_file_and_valid_json(tmp_path):
    security.append_audit_event(tmp_path, "login", {"user": "alice"})
    lines = _read_audit_lines(tmp_path)
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert isinstance(record["timestamp"], float)
    assert record["event"] == "login"
    assert record["details"] == {"user": "alice"}


def test_append_audit_event_creates_output_directory(tmp_path):
    # tmp_path/output does not exist yet; the function must create it.
    assert not (tmp_path / "output").exists()
    security.append_audit_event(tmp_path, "evt")
    assert (tmp_path / "output" / "audit_log.jsonl").exists()


def test_append_audit_event_default_none_details(tmp_path):
    security.append_audit_event(tmp_path, "evt")
    record = json.loads(_read_audit_lines(tmp_path)[0])
    assert record["details"] == {}


def test_append_audit_event_appends_multiple_lines(tmp_path):
    security.append_audit_event(tmp_path, "one")
    security.append_audit_event(tmp_path, "two")
    lines = _read_audit_lines(tmp_path)
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "one"
    assert json.loads(lines[1])["event"] == "two"


def test_append_audit_event_redacts_secret_by_default(tmp_path):
    security.append_audit_event(tmp_path, "auth", {"api_key": "sk-abc123"})
    line = _read_audit_lines(tmp_path)[0]
    assert "sk-abc123" not in line
    assert "***" in line


def test_append_audit_event_redact_false_leaves_secret(tmp_path):
    security.append_audit_event(tmp_path, "auth", {"api_key": "sk-abc123"}, redact=False)
    line = _read_audit_lines(tmp_path)[0]
    assert "sk-abc123" in line


def test_append_audit_event_swallows_directory_creation_failure(tmp_path):
    # base_dir is an existing regular file, so base_dir/"output" cannot be
    # created (mkdir raises). The function must swallow the exception.
    file_as_base = tmp_path / "not_a_dir"
    file_as_base.write_text("i am a file", encoding="utf-8")
    # Should not raise.
    security.append_audit_event(file_as_base, "evt", {"api_key": "sk-abc123"})
    # The pre-existing file is left intact.
    assert file_as_base.read_text(encoding="utf-8") == "i am a file"


# ---------------------------------------------------------------------------
# extract_bearer_or_header
# ---------------------------------------------------------------------------

def test_extract_bearer_basic():
    assert security.extract_bearer_or_header({"Authorization": "Bearer xyz"}) == "xyz"


def test_extract_bearer_case_insensitive_prefix():
    assert security.extract_bearer_or_header({"Authorization": "bearer xyz"}) == "xyz"


def test_extract_bearer_extra_whitespace_is_stripped():
    # "Bearer  xyz" -> split(' ', 1)[1] == " xyz" -> .strip() == "xyz".
    assert security.extract_bearer_or_header({"Authorization": "Bearer  xyz"}) == "xyz"


def test_extract_bearer_other_scheme_falls_through_to_empty():
    # "Basic xyz" does not match the bearer prefix and there is no X-API-Token.
    assert security.extract_bearer_or_header({"Authorization": "Basic xyz"}) == ""


def test_extract_bearer_falls_back_to_x_api_token():
    headers = {"X-API-Token": "  tok123  "}
    assert security.extract_bearer_or_header(headers) == "tok123"


def test_extract_bearer_basic_scheme_falls_back_to_x_api_token():
    headers = {"Authorization": "Basic xyz", "X-API-Token": "tok123"}
    assert security.extract_bearer_or_header(headers) == "tok123"


def test_extract_bearer_none_headers_returns_empty():
    assert security.extract_bearer_or_header(None) == ""


def test_extract_bearer_empty_dict_returns_empty():
    assert security.extract_bearer_or_header({}) == ""
