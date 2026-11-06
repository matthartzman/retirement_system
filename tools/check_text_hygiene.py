"""Text-hygiene gate: stray control characters and wrong line endings.

Two classes of error keep recurring when files are written by ad-hoc scripts
(heredocs, Python one-liners, PowerShell here-strings) instead of the Edit tool:

1. A regex written in a NON-raw Python string: "\\bword\\b" is really two literal
   backspace characters (0x08), so the pattern silently matches nothing. The
   same script-escaping accident leaves \\x07, \\x0c or \\x0b in a string.
   Two checks catch it: a byte scan of text files, and for .py files an AST scan
   of every string constant (the "\\b" case is an escape in the SOURCE, so only
   the parsed value shows it).
2. Wrong newline treatment. The repository stores LF (the index is LF except
   where .gitattributes says otherwise); on Windows with core.autocrlf the
   working copy is CRLF. A script that writes LF into a CRLF working file (or
   the reverse) leaves a MIXED file, and one that bypasses autocrlf can commit
   CRLF. Checks: mixed line endings in the working tree or the index, a lone CR,
   and CRLF stored in the index.

Usage:
    python tools/check_text_hygiene.py              # every tracked text file (index + working tree)
    python tools/check_text_hygiene.py path [path]  # just those working-tree files (post-edit hook)
Exit 0 = clean, 1 = findings (printed with file, line and a fix hint).
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".json", ".md", ".yml", ".yaml", ".toml",
    ".html", ".css", ".ps1", ".bat", ".cmd", ".sh", ".txt", ".cfg", ".ini",
}

# Control characters that never belong in source text. Tab (9), LF (10) and CR (13)
# are handled separately; ESC (27) is flagged too -- write "\x1b" as an escape.
_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Characters that signal a mangled escape when they appear in a Python string VALUE.
_BAD_STRING_CHARS = {chr(8): "backspace (\\b in a non-raw string)", chr(7): "bell (\\a)",
                     chr(11): "vertical tab (\\v)", chr(12): "form feed (\\f)"}

# path -> reason. Add an entry only for a file that must legitimately contain the
# character (e.g. a fixture that tests control-character handling).
ALLOWLIST: dict[str, str] = {
    "tools/check_text_hygiene.py": "documents the characters it detects",
    "tests/test_text_hygiene_regression.py": "builds bad inputs to prove the checker catches them",
}


def check_bytes(name: str, data: bytes, *, index: bool = False) -> list[str]:
    """Findings for one file's bytes. ``index`` = the stored (committed) form."""
    out: list[str] = []
    if b"\x00" in data[:8192]:
        return out  # binary
    m = _CONTROL.search(data)
    if m:
        line = data.count(b"\n", 0, m.start()) + 1
        out.append(f"{name}:{line}: control character 0x{data[m.start()]:02x} in text file "
                   "(a script's escaping produced it -- use a raw string r'\\bword\\b', or the Edit tool)")
    crlf = data.count(b"\r\n")
    lone_cr = data.count(b"\r") - crlf
    lf_only = data.count(b"\n") - crlf
    if lone_cr:
        out.append(f"{name}: {lone_cr} lone CR (old-Mac line ending) -- rewrite with LF")
    if crlf and lf_only:
        out.append(f"{name}: MIXED line endings ({crlf} CRLF, {lf_only} LF). Rewrite the whole file with "
                   "one ending; scripts must open files with newline='' and preserve the existing ending")
    elif index and crlf:
        out.append(f"{name}: CRLF stored in the repository (index must be LF; "
                   "check core.autocrlf / .gitattributes, or normalise the file)")
    return out


def check_python_strings(name: str, data: bytes) -> list[str]:
    """Flag string constants whose VALUE holds backspace/bell/VT/FF (e.g. "\\b" in a non-raw string)."""
    try:
        tree = ast.parse(data.decode("utf-8", errors="replace"), filename=name)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for ch, label in _BAD_STRING_CHARS.items():
                if ch in node.value:
                    out.append(f"{name}:{node.lineno}: string contains {label}: {node.value[:60]!r} "
                               "-- make it a raw string (r'...') if it is a regex")
                    break
    return out


def check_file(name: str, data: bytes, *, index: bool = False) -> list[str]:
    if name in ALLOWLIST:
        return []
    findings = check_bytes(name, data, index=index)
    if name.endswith(".py"):
        findings += check_python_strings(name, data)
    return findings


def _tracked_text_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    names = [n for n in out.stdout.decode("utf-8", errors="replace").split("\0") if n]
    return [n for n in names if Path(n).suffix.lower() in TEXT_SUFFIXES]


def _index_eol_findings() -> list[str]:
    """One ``git ls-files --eol`` call: index (i/) line-ending state of every tracked file."""
    out = subprocess.run(["git", "ls-files", "--eol", "-z"], cwd=ROOT, capture_output=True)
    findings = []
    for rec in out.stdout.decode("utf-8", errors="replace").split(chr(0)):
        if not rec:
            continue
        meta, _, name = rec.partition(chr(9))
        idx = meta.split()[0]  # e.g. "i/lf"
        if Path(name).suffix.lower() not in TEXT_SUFFIXES or name in ALLOWLIST:
            continue
        if idx == "i/crlf":
            findings.append(f"{name}: CRLF stored in the repository (index must be LF; "
                            "check core.autocrlf / .gitattributes, or normalise the file)")
        elif idx == "i/mixed":
            findings.append(f"{name}: MIXED line endings stored in the repository")
    return findings


def scan_repo() -> list[str]:
    findings: list[str] = []
    for name in _tracked_text_files():
        p = ROOT / name
        if p.is_file():
            findings += check_file(name, p.read_bytes())
    for f in _index_eol_findings():
        if f not in findings:
            findings.append(f)
    return findings


def main(argv: list[str]) -> int:
    if argv:
        findings = []
        for a in argv:
            p = Path(a)
            p = p if p.is_absolute() else ROOT / p
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
                try:
                    rel = p.relative_to(ROOT).as_posix()
                except ValueError:
                    rel = p.as_posix()
                findings += check_file(rel, p.read_bytes())
    else:
        findings = scan_repo()
    for f in findings:
        print(f)
    if findings:
        print(f"\ntext-hygiene: {len(findings)} finding(s).")
        return 1
    print("text-hygiene: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
