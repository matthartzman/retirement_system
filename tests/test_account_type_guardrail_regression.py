"""Item 1.16 / finding F9: an account name that matches no recognized
type-indicating suffix must BLOCK a build with a clear error, not silently
model the account as taxable.

Mirrors the two-layer structure of
test_residence_state_required_for_build_regression.py (the sibling
silent-wrongness fix, item 1.10): unit-level checks against
`src.core._infer_type` / `build_registry_from_balances` / `build_registry_from_json`,
plus an integration-level check against the real `parse_client` build entry
point using a staged copy of the frozen fixture.

Before this fix, `src.core._infer_type` fell through to `'taxable'` for any
account name it did not recognize (a typo'd suffix, a name from a household
this tool has never modeled), so a mistyped or unsupported account silently
got the wrong tax treatment and RMD behavior with nothing on any report
saying so.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"


def _staged_workspace(*, rename_account=None, rename_to=None):
    """Copy the frozen fixture into a temp workspace, optionally renaming one
    account (in client_holdings.csv) to a different identifier."""
    workspace = Path(tempfile.mkdtemp(prefix="account_type_guardrail_test_"))
    (workspace / "input").mkdir(parents=True)
    for f in sorted(FROZEN_DIR.iterdir()):
        if f.is_file():
            shutil.copy(f, workspace / "input" / f.name)

    if rename_account is not None:
        holdings = workspace / "input" / "client_holdings.csv"
        text = holdings.read_text(encoding="utf-8")
        # Simple whole-token replace of the leading CSV column value.
        lines = text.splitlines(keepends=True)
        out = []
        for line in lines:
            if line.startswith(f"{rename_account},"):
                out.append(rename_to + line[len(rename_account):])
            else:
                out.append(line)
        holdings.write_text("".join(out), encoding="utf-8")

    return workspace


def _parse_from_workspace(workspace):
    from src.data_io import load_csv, parse_client

    prev_root = os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT")
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace)
    try:
        data = load_csv(workspace / "input" / "client_data.csv")
        return parse_client(data, "")
    finally:
        if prev_root is None:
            os.environ.pop("RETIREMENT_SYSTEM_WORKSPACE_ROOT", None)
        else:
            os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = prev_root


# --------------------------------------------------------------------------
# _infer_type -- unit level
# --------------------------------------------------------------------------


def test_recognized_suffixes_still_infer_correctly():
    from src.core import _infer_type

    assert _infer_type("Member_1_401k") == "401k"
    assert _infer_type("Member_1_403b") == "403b"
    assert _infer_type("Member_1_Roth") == "roth_ira"
    assert _infer_type("Member_1_IRA") == "traditional_ira"
    assert _infer_type("Member_1_Trust") == "trust"
    assert _infer_type("Member_1_HSA") == "hsa"
    assert _infer_type("Family_Checking") == "checking"
    assert _infer_type("Grandkid_529") == "529"
    assert _infer_type("Member_1_Taxable") == "taxable"
    assert _infer_type("Member_1_Brokerage") == "taxable"
    assert _infer_type("Member_1_Investment") == "taxable"


def test_unrecognized_account_name_raises_and_names_the_account():
    from src.core import _infer_type

    with pytest.raises(ValueError) as exc:
        _infer_type("Member_1_Weird")
    message = str(exc.value)
    assert "Member_1_Weird" in message
    assert "_401k" in message and "_taxable" in message, (
        "error must list the recognized suffixes so the user knows how to fix it"
    )


def test_typo_of_a_known_suffix_still_raises():
    """A near-miss typo (e.g. `_iras` instead of `_ira`) must not silently
    match a substring by accident and must not fall back to taxable."""
    from src.core import _infer_type

    with pytest.raises(ValueError):
        _infer_type("Member_1_Retirement_Account")


# --------------------------------------------------------------------------
# build_registry_from_balances -- the function parse_client() actually calls
# --------------------------------------------------------------------------


def test_build_registry_from_balances_raises_on_unrecognized_account():
    from src.core import build_registry_from_balances

    members = [{"name": "Alex", "nickname": "Alex"}]
    with pytest.raises(ValueError) as exc:
        build_registry_from_balances({"Member_1_Weird": 100_000.0}, members)
    assert "Member_1_Weird" in str(exc.value)


def test_build_registry_from_balances_accepts_recognized_accounts():
    from src.core import build_registry_from_balances

    members = [{"name": "Alex", "nickname": "Alex"}]
    registry = build_registry_from_balances(
        {"Member_1_IRA": 100_000.0, "Member_1_Taxable": 50_000.0}, members
    )
    by_id = {a["id"]: a for a in registry}
    assert by_id["Member_1_IRA"]["acct_type"] == "traditional_ira"
    assert by_id["Member_1_Taxable"]["acct_type"] == "taxable"


# --------------------------------------------------------------------------
# build_registry_from_json -- the wizard JSON path (explicit acct_type field)
# --------------------------------------------------------------------------


def test_build_registry_from_json_raises_on_unrecognized_acct_type():
    from src.core import build_registry_from_json

    members = [{"name": "Alex", "nickname": "Alex"}]
    accounts = [{"id": "acct_1", "acct_type": "crypto_wallet", "balance": 10_000}]
    with pytest.raises(ValueError) as exc:
        build_registry_from_json(accounts, members)
    message = str(exc.value)
    assert "crypto_wallet" in message
    assert "acct_1" in message


def test_build_registry_from_json_still_defaults_missing_acct_type_to_taxable():
    """Omitting acct_type entirely (not present in the payload at all) is
    unrelated to this guardrail -- it is the wizard's own documented default,
    not a typo -- so that leniency is intentionally preserved."""
    from src.core import build_registry_from_json

    members = [{"name": "Alex", "nickname": "Alex"}]
    accounts = [{"id": "acct_1", "balance": 10_000}]
    registry = build_registry_from_json(accounts, members)
    assert registry[0]["acct_type"] == "taxable"


# --------------------------------------------------------------------------
# Real build entry point -- integration level, against the frozen fixture
# --------------------------------------------------------------------------


def test_parse_client_blocks_a_real_build_with_an_unrecognized_account_name():
    workspace = _staged_workspace(rename_account="Member_1_IRA", rename_to="Member_1_Weird")
    try:
        with pytest.raises(ValueError) as exc:
            _parse_from_workspace(workspace)
        assert "Member_1_Weird" in str(exc.value)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_parse_client_still_builds_normally_for_the_frozen_household():
    """Golden-master safety check for this ticket at unit-test speed, ahead of
    the full frozen golden-master suite: the unmodified fixture's account
    names must all still be recognized."""
    workspace = _staged_workspace()
    try:
        c = _parse_from_workspace(workspace)
        assert sum(c["balances"].values()) > 0
        assert all(a["acct_type"] for a in c["account_registry"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
