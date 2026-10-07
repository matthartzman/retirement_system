import contextlib
import csv
import tempfile
import unittest
from pathlib import Path

import pytest

from tests.plan_fixture import make_plan

from src.schema_registry import PLAN_FILES, validate_rows
from src.workspace_context import workspace_input_dir
try:
    from src.server import workbook_routes  # noqa: F401 - registers routes
    from src.server.app_core import app
except BaseException as exc:  # pragma: no cover - startup diagnostics
    app = None
    SERVER_IMPORT_ERROR = exc
else:
    SERVER_IMPORT_ERROR = None

ROOT = Path(__file__).resolve().parents[1]
# Resolve via the same workspace-root lookup the /api routes use (rather than
# a hardcoded ROOT/"input"), so this test reads/writes the same file the
# routes under test actually touch even when RETIREMENT_SYSTEM_WORKSPACE_ROOT
# redirects writable data elsewhere (as tests/conftest.py does, to keep the
# test suite from mutating the real client input files).
INPUT = workspace_input_dir()


@contextlib.contextmanager
def _isolated_workspace():
    """A fixture plan in its own workspace: the routes edit its plan file, not the session's."""
    with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
        plan = make_plan(Path(tmp) / "ws")
        mp.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
        mp.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
        yield plan


class InsuranceDeleteAndSaveValidationTests(unittest.TestCase):
    def setUp(self):
        if self._testMethodName.startswith(('test_save_endpoint', 'test_insurance_policy_delete')) and app is None:
            self.skipTest(f'Server UI dependencies unavailable: {SERVER_IMPORT_ERROR}')

    def test_current_input_rows_validate_before_save(self):
        rows = []
        for name in PLAN_FILES:
            path = INPUT / name
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8-sig") as f:
                rows.extend(csv.DictReader(f))
        self.assertEqual([], validate_rows(rows))

    def test_save_endpoint_accepts_percent_rows_stored_as_human_percent(self):
        with _isolated_workspace():
            client = app.test_client()
            fetched = client.get("/api/config/rows", headers={"X-User-Role": "admin"})
            self.assertEqual(200, fetched.status_code)
            row = next(r for r in fetched.get_json()["rows"] if r.get("label") == "applicable_pct_cap")
            saved = client.post(
                "/api/config/rows",
                json={"updates": [{"row_index": row["row_index"], "value": row["value"]}]},
                headers={"X-User-Role": "admin"},
            )
            self.assertEqual(200, saved.status_code, saved.get_data(as_text=True))
            self.assertTrue(saved.get_json().get("success"))

    def test_insurance_policy_delete_route_removes_entire_policy_section(self):
        with _isolated_workspace() as plan:
            self.assertIn("Life_Term_Matthew", plan.store_data()["Insurance In Force"])
            client = app.test_client()
            response = client.post(
                "/api/insurance-policy/delete",
                json={"subsection": "Life_Term_Matthew"},
                headers={"X-User-Role": "admin"},
            )
            self.assertEqual(200, response.status_code, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertTrue(payload.get("success"))
            self.assertGreater(payload.get("rows_removed", 0), 0)
            self.assertNotIn("Life_Term_Matthew", plan.store_data()["Insurance In Force"])


if __name__ == "__main__":
    unittest.main()
