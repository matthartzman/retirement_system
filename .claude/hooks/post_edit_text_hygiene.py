"""PostToolUse guard: check a just-written/edited file for stray control
characters (e.g. a literal backspace where \\b belonged) and mixed line endings.

Exit 2 sends the findings back to the model so it fixes the file immediately,
instead of the mistake surviving until CI. Silent (exit 0) when clean or when
the edited file is not a text type the checker knows.
"""
import json
import subprocess
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    path = (data.get("tool_input") or {}).get("file_path")
    if not path:
        return 0
    proc = subprocess.run(
        [sys.executable, "tools/check_text_hygiene.py", path], capture_output=True, text=True
    )
    if proc.returncode == 0:
        return 0
    sys.stderr.write("Text-hygiene problem in the file you just wrote:\n" + proc.stdout + "\n"
                     "Fix it now (raw strings for regexes; one consistent line ending).\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
