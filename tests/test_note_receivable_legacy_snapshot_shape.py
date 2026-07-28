"""#247 root cause: a plan_snapshots row written before the "repeatable notes"
feature (see data_io.py's Note Receivable comment) stored one note under
subsection "Summary" with its interest schedule under "Interest by Year",
instead of the current "Note 1" / "Note 1 Interest" convention. parse_client()
only recognized subsections matching ^Note \\d+$, so a plan loaded from that
stale shape silently produced an EMPTY note_items -- zero note income/balance
everywhere (cash flow, net worth, workbook, in-app pages), with no error
pointing at why. Reproduced live via load_active_config() against a real
household's DB and confirmed fixed by regenerating the snapshot AND by this
backward-compat parsing fallback, which must keep working even if a snapshot
never gets refreshed.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

from src.data_io import load_csv, parse_client

ROOT = Path(__file__).resolve().parents[1]


def _base_data():
    return copy.deepcopy(load_csv(ROOT / "input" / "client_data.csv"))


class NoteReceivableLegacySnapshotShapeTests(unittest.TestCase):
    def test_current_note_n_shape_parses(self):
        data = _base_data()
        data["Note Receivable"] = {
            "Note 1": {
                "name": "Test Note",
                "face_value": "100000",
                "first_payment": "1/2/2026",
                "last_payment": "1/2/2027",
                "annual_principal_base_period": "45000",
                "final_principal": "45000",
            },
            "Note 1 Interest": {"2026": "5000", "2027": "2500"},
        }
        c = parse_client(data, "")
        self.assertEqual(len(c["note_items"]), 1)
        note = c["note_items"][0]
        self.assertEqual(note["name"], "Test Note")
        self.assertEqual(note["face_value"], 100000.0)
        self.assertEqual(note["interest_by_year"].get(2026), 5000.0)

    def test_legacy_summary_shape_still_parses(self):
        data = _base_data()
        data["Note Receivable"] = {
            "Summary": {
                "name": "Legacy Note",
                "face_value": "200000",
                "first_payment": "1/2/2026",
                "last_payment": "1/2/2027",
                "annual_principal_base_period": "90000",
                "final_principal": "90000",
            },
            "Interest by Year": {"2026": "8000", "2027": "4000"},
        }
        c = parse_client(data, "")
        self.assertEqual(
            len(c["note_items"]), 1,
            "a legacy single-note snapshot (subsection 'Summary') must still "
            "produce one note, not be silently dropped",
        )
        note = c["note_items"][0]
        self.assertEqual(note["name"], "Legacy Note")
        self.assertEqual(note["face_value"], 200000.0)
        self.assertEqual(
            note["interest_by_year"].get(2026), 8000.0,
            "interest must be read from 'Interest by Year' for the legacy shape",
        )
        # And the scalar legacy aggregates (still used by optimization.py /
        # the balance-sheet fallback) must reflect it too.
        self.assertEqual(c["note_face"], 200000.0)
        self.assertEqual(c["note_interest"][2026], 8000.0)

    def test_missing_note_receivable_section_yields_no_notes(self):
        data = _base_data()
        data.pop("Note Receivable", None)
        c = parse_client(data, "")
        self.assertEqual(c["note_items"], [])
        self.assertEqual(c["note_face"], 0.0)


if __name__ == "__main__":
    unittest.main()
