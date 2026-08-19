"""Contract tests for registering client_hsa_schedule.csv as a flat plan-data table.

client_hsa_schedule.csv is a per-row override table (same category as
client_holdings.csv / client_liabilities.csv): no section/subsection/label
structure, no YAML counterpart, not part of the sectioned client_data.csv
bundle. This test file proves the three registration sites that let the file
be read, written, sync'd, and blanked correctly by the existing plan-data
infrastructure:

  1. src/server/plan_data_files.py PLAN_DATA_CSV_FILES -- the load-bearing
     list that feeds PLAN_DATA_FILE_SET, the gate _normalize_plan_data_file_name
     checks in src/server/app_core.py before _read_plan_data_file /
     _write_plan_data_file will touch a file at all.
  2. src/local_plan_data_sync.py PLAN_DATA_CSV_FILES -- the separate,
     independently-hardcoded list used for folder sync / download.
  3. src/server/app_core.py _blank_hsa_schedule_csv -- the "Start New Plan"
     blank-template function, mirroring _blank_holdings_csv / _blank_liabilities_csv.
"""
from __future__ import annotations

import csv
import io
import unittest

from src.server import app_core, plan_data_files
from src import local_plan_data_sync

HSA_SCHEDULE_HEADER = ["year", "optimizer_amount", "override_amount", "locked", "note"]


class HsaScheduleRegistrationTests(unittest.TestCase):
    def test_registered_in_server_plan_data_files(self):
        self.assertIn("client_hsa_schedule.csv", plan_data_files.PLAN_DATA_CSV_FILES)

    def test_registered_in_local_plan_data_sync(self):
        self.assertIn("client_hsa_schedule.csv", local_plan_data_sync.PLAN_DATA_CSV_FILES)

    def test_registered_in_plan_data_file_set_gate(self):
        # Cheap proxy for "the DB-canonical read/write gate accepts it":
        # _normalize_plan_data_file_name (used by both _read_plan_data_file and
        # _write_plan_data_file) checks membership in this exact set.
        self.assertIn("client_hsa_schedule.csv", app_core.PLAN_DATA_FILE_SET)


class BlankHsaScheduleCsvTests(unittest.TestCase):
    def test_blank_with_real_content_returns_header_only(self):
        content = (
            "year,optimizer_amount,override_amount,locked,note\n"
            "2026,5000,,FALSE,\n"
            "2027,5200,4800,TRUE,manual override\n"
        )
        result = app_core._blank_hsa_schedule_csv(content)
        rows = list(csv.reader(io.StringIO(result)))
        self.assertEqual(rows, [HSA_SCHEDULE_HEADER])

    def test_blank_with_empty_content_falls_back_to_hardcoded_header(self):
        result = app_core._blank_hsa_schedule_csv("")
        rows = list(csv.reader(io.StringIO(result)))
        self.assertEqual(rows, [HSA_SCHEDULE_HEADER])

    def test_blank_dispatch_registered_for_client_hsa_schedule_csv(self):
        # _make_blank_plan_files must route this file name through
        # _blank_hsa_schedule_csv rather than leaving stale template rows in
        # place (the way _blank_holdings_csv / _blank_liabilities_csv are
        # routed for their own flat tables).
        files = app_core._make_blank_plan_files()
        self.assertIn("client_hsa_schedule.csv", files)
        rows = list(csv.reader(io.StringIO(files["client_hsa_schedule.csv"])))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], HSA_SCHEDULE_HEADER)


if __name__ == "__main__":
    unittest.main()
