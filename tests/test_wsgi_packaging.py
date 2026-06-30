from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WsgiPackagingTests(unittest.TestCase):
    def test_wsgi_entry_point_lives_with_server_package(self):
        root_wsgi = ROOT / "wsgi.py"
        server_wsgi = ROOT / "src" / "server" / "wsgi.py"
        self.assertFalse(root_wsgi.exists(), "wsgi.py must not be packaged at repository/package root")
        self.assertTrue(server_wsgi.exists(), "Canonical WSGI entry point must be src/server/wsgi.py")
        text = server_wsgi.read_text(encoding="utf-8")
        self.assertIn("application = create_app()", text)

    def test_waitress_runner_is_deprecated(self):
        text = (ROOT / "tools" / "run_wsgi_server.py").read_text(encoding="utf-8")
        self.assertIn("deprecated", text.lower())


if __name__ == "__main__":
    unittest.main()
