"""PreToolUse guard: refuse whole-file Reads of the repo's largest files.

Reading one of these linearly can cost more context than the task warrants, and
the cost is paid on every subsequent turn of that session. The guard denies the
call with a reason that names the cheap alternative, so the model re-issues a
bounded Read instead of being stuck.

Denial is recoverable by design: a chunked read with offset/limit is allowed, so
a genuinely necessary full pass still works, just in bounded pieces.

Companion to the "Reading Large Files" table in .claude/claude.md. Keep the two
in sync -- that table tells the model where to enter each file, this enforces it.
"""

import json
import sys

# basename -> where to enter the file instead. Mirrors .claude/claude.md.
# module_catalog.py is deliberately absent: it is small enough to read whole
# when the task is catalog-wide, which several workstreams legitimately are.
GUARDED = {
    "dashboard.js": "7,287 lines. Grep the function name first; renderOptionalFunctions() is ~35 lines of it.",
    "dashboard_decomp_row_model.js": "5,188 lines. Grep only -- this file is never worth reading whole.",
    "dashboard_decomp_housing_optimizer.js": "1,984 lines. Grep the panel or render function you need.",
    "workbook_builder.py": "1,443 lines. Grep the builder or merge function.",
    "dashboard_decomp_housing_scenarios.js": "1,397 lines. Read only the estimateHousingFromState region.",
    "workbook_common.py": "1,161 lines. Grep the table or rename function.",
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # Never block on a payload we cannot parse.

    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or ""
    if not isinstance(raw_path, str) or not raw_path:
        return 0

    basename = raw_path.replace("\\", "/").rsplit("/", 1)[-1]
    hint = GUARDED.get(basename)
    if hint is None:
        return 0

    # A bounded read is exactly what we want; let it through.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{basename} is a large file and this Read has no offset/limit. {hint} "
                    "Then Read with offset/limit around the hit, or dispatch an Explore "
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
