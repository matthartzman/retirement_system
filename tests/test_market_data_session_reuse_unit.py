"""Price fetches must share one requests.Session.

Each bare requests.get builds a fresh connection pool and SSLContext, which
re-reads the CA bundle -- measured at 30 CA-bundle loads in a single build.
"""
from __future__ import annotations

import unittest

import src.market_data as md


class SessionReuse(unittest.TestCase):
    def test_session_is_a_singleton(self):
        first = md._session()
        if first is None:
            self.skipTest("requests is not installed in this environment")
        self.assertIs(first, md._session())

    def test_session_exposes_get(self):
        sess = md._session()
        if sess is None:
            self.skipTest("requests is not installed in this environment")
        self.assertTrue(hasattr(sess, "get"))


if __name__ == '__main__':
    unittest.main()
