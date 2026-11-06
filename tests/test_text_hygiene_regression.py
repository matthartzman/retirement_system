"""Text-hygiene gate (control characters and line endings).

Prevents two recurring script-writing accidents: a regex pattern containing a
literal backspace (0x08) because "\\b" was written in a non-raw string, and
files left with mixed or wrong line endings. See tools/check_text_hygiene.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import check_text_hygiene as th  # noqa: E402

BS = chr(8)


def test_repository_text_files_are_clean():
    findings = th.scan_repo()
    assert findings == [], "\n" + "\n".join(findings)


def test_literal_backspace_in_a_file_is_caught():
    data = ("pattern = re.compile('" + BS + "word" + BS + "')\n").encode()
    assert any("control character 0x08" in f for f in th.check_bytes("x.py", data))


def test_backspace_from_a_non_raw_regex_string_is_caught_by_the_ast_scan():
    # In the SOURCE this is the two characters backslash-b; the parsed value holds 0x08.
    src = b'import re\nre.search("\\bword\\b", text)\n'
    assert th.check_python_strings("x.py", src), "non-raw \\b regex was not flagged"


def test_raw_regex_string_is_not_flagged():
    src = b'import re\nre.search(r"\\bword\\b", text)\n'
    assert th.check_python_strings("x.py", src) == []


def test_mixed_line_endings_are_caught():
    assert any("MIXED" in f for f in th.check_bytes("x.md", b"a\r\nb\nc\r\n"))


def test_lone_cr_is_caught():
    assert any("lone CR" in f for f in th.check_bytes("x.md", b"a\rb\n"))


def test_crlf_in_the_index_is_caught_but_working_tree_crlf_is_fine():
    data = b"a\r\nb\r\n"
    assert th.check_bytes("x.py", data) == []  # autocrlf working copy
    assert any("CRLF stored" in f for f in th.check_bytes("x.py", data, index=True))


def test_clean_lf_file_passes():
    assert th.check_file("x.py", b"x = 1\n") == []
