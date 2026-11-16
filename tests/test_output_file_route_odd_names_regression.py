"""/files/<name> with a NUL byte or other unresolvable name is a clean refusal, not an unhandled error."""
from __future__ import annotations

from src.server_services import report_service


def test_a_nul_byte_in_the_name_is_refused(tmp_path):
    for name in ("plan.rpx\x00.txt", "a\x00", "con\x00"):
        payload, status = report_service.local_output_file_payload(tmp_path, name)
        assert status in (400, 403, 404) and payload["success"] is False
