"""Finding SEC-5 (system review 2026-09-07, Wave 6 item W6-1):
base_service.status_payload()'s "features" advertisement claimed
"encrypted_api_keys": True in the same JSON response as an "encryption"
sub-object reporting "encrypted": False -- a flatly self-contradicting pair
in one API payload, not just an ambiguously-named field.
"""
from pathlib import Path

from src.secrets_store import encryption_status
from src.server_services.base_service import status_payload


class _Cfg:
    app_mode = "LOCAL"


def test_status_payload_never_claims_encrypted_api_keys_while_reporting_unencrypted(tmp_path):
    base_dir = Path(tmp_path)
    output_dir = base_dir / "output"
    payload = status_payload(
        version="12.0.0",
        cfg=_Cfg(),
        base_dir=base_dir,
        output_dir=output_dir,
        encryption=encryption_status(),
    )
    assert payload["encryption"]["encrypted"] is False
    assert payload["features"]["encrypted_api_keys"] == payload["encryption"]["encrypted"], (
        "features.encrypted_api_keys must never claim encryption the secrets "
        "store doesn't actually provide -- it must track encryption.encrypted, "
        "not an independent hardcoded value"
    )
