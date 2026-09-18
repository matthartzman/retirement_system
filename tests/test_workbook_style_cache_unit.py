"""Repeated cell styles should reuse one object instead of rebuilding it.

write_cell is called ~16,500 times per build; openpyxl hashes every style
object to de-duplicate it into the workbook style table.
"""
from __future__ import annotations

import unittest

from src.reporting import workbook_common as wc


class StyleCache(unittest.TestCase):
    def test_identical_font_requests_return_the_same_object(self):
        self.assertIs(wc._cached_font(True, '000000'), wc._cached_font(True, '000000'))

    def test_different_font_requests_return_different_objects(self):
        self.assertIsNot(wc._cached_font(True, '000000'), wc._cached_font(False, '000000'))

    def test_identical_alignment_requests_return_the_same_object(self):
        self.assertIs(wc._cached_alignment('left'), wc._cached_alignment('left'))

    def test_font_carries_the_requested_attributes(self):
        f = wc._cached_font(True, 'FF0000')
        self.assertEqual(f.name, 'Arial')
        self.assertEqual(f.size, 10)
        self.assertTrue(f.bold)


if __name__ == '__main__':
    unittest.main()
