"""PreToolUse guard: refuse whole-file Reads of large files.

Reading a large file linearly can cost more context than the task warrants, and
the cost is paid on every subsequent turn of that session. The guard measures
the file's line count at call time (so it never goes stale and covers files that
grow past the threshold without any edit here) and, when it is at or over
LINE_THRESHOLD, denies a Read that has no offset/limit. The denial names the
cheap alternative, so the model re-issues a bounded Read instead of being stuck.

Denial is recoverable by design: a chunked read with offset/limit is allowed, so
a genuinely necessary full pass still works, just in bounded pieces.

Companion to the "Reading Large Files" bands in .claude/claude.md (DOC-005, W1-08).
The per-file entry hints below carry no line counts for that reason.
"""

import json
import sys

# A file at or over this many lines is guarded. module_catalog.py (~2,500 lines)
# and the large frontend/reporting modules are covered by the threshold alone.
LINE_THRESHOLD = 1500

# Files that are never worth reading as text, whatever their size.
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".xlsx", ".zip", ".db", ".rpx", ".ipynb")

# basename -> where to enter the file instead. No line counts: the hook measures them.
HINTS = {
    "dashboard.js": "Grep the function name first; renderOptionalFunctions() is ~35 lines of it.",
    "dashboard_decomp_row_model.js": "Grep only -- this file is never worth reading whole.",
    "dashboard_decomp_housing_optimizer.js": "Grep the panel or render function you need.",
    "dashboard_decomp_housing_scenarios.js": "Read only the estimateHousingFromState region.",
    "workbook_builder.py": "Grep the builder or merge function.",
    "workbook_common.py": "Grep the table or rename function.",
    "module_catalog.py": "Grep the module key; read whole only for a catalog-wide task, in offset/limit chunks.",
}
DEFAULT_HINT = "Grep for the function, class or heading you need first."


def count_lines(path: str) -> int | None:
    """Line count of ``path`` right now, or None if it cannot be read."""
    try:
        with open(path, "rb") as handle:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 20), b""))
    except OSError:
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # Never block on a payload we cannot parse.

    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or ""
    if not isinstance(raw_path, str) or not raw_path:
        return 0
    if raw_path.lower().endswith(SKIP_SUFFIXES):
        return 0

    # A bounded read is exactly what we want; let it through.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return 0

    lines = count_lines(raw_path)
    if lines is None or lines < LINE_THRESHOLD:
        return 0

    basename = raw_path.replace("\\", "/").rsplit("/", 1)[-1]
    hint = HINTS.get(basename, DEFAULT_HINT)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{basename} is {lines:,} lines (guard threshold {LINE_THRESHOLD:,}) and this Read has no "
                    f"offset/limit. {hint} Then Read with offset/limit around the hit, or dispatch an Explore "
                    "subagent so the file's bulk never enters this session's context. "
                    "If you truly need the whole file, read it in bounded chunks."
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
