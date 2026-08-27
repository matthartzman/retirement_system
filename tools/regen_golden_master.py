#!/usr/bin/env python
"""Golden-master recovery tool for the frozen sample-plan pins.

Ticket 286. See ``documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`` for the
decision tree this tool supports. This script never reimplements the
measurement itself -- every subcommand that needs a computed value invokes
``tests/test_frozen_sample_plan_golden_master_regression.py``'s own
``__main__`` regen block (via ``py -3.14 -m tests.test_frozen_sample_plan_golden_master_regression``)
and parses its two printed lines. That block is hermetic (frozen fixture,
frozen date, frozen prices) and is the single source of truth for how the
pins are computed; a second, hand-rolled measurement path would be exactly
the kind of drift this tool exists to prevent.

Subcommands
-----------
measure
    Print the currently-computed values and the delta vs. the pins recorded
    in the test file. Read-only, always safe to run.

verify-endpoint <sha>
    Check out ``<sha>`` into a **detached git worktree**, run the frozen
    golden-master test there, and report whether that commit's OWN pin held.
    This mechanizes trap #1 from the 2026-08-10 postmortem: ``git bisect``
    never re-tests the "good" endpoint you hand it, so an already-bad
    endpoint silently poisons the whole bisect range. Run this against your
    candidate "good" commit BEFORE bisecting. Refuses to run against a dirty
    working tree.

origin <value>
    Run ``git log --follow -S<value>`` against the pin file and print
    candidate commits. Mechanizes trap #2: a plain ``git log -S`` (without
    ``--follow``) can name the wrong origin commit when a file rename makes
    the value look newly added.

regen --reason <file>
    Recompute the pins via the reused measurement, rewrite
    ``PINNED_TERMINAL_NW`` / ``PINNED_LIFETIME_TAX`` and the machine-checked
    PROVENANCE line above them, and append a dated entry to
    ``documentation/GOLDEN_MASTER_CHANGELOG.md``. Refuses without
    ``--reason``, and refuses if the reason text is empty, too short, or a
    recognizable placeholder -- a pin must never move silently.

Every subcommand sets ``RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1``
internally. A forgotten env var is how ordinary price drift gets
misdiagnosed as an engine change (see the module docstring of the test file
itself, and ``documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md``).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = ROOT / "tests" / "test_frozen_sample_plan_golden_master_regression.py"
CHANGELOG_FILE = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"
REGEN_MODULE = "tests.test_frozen_sample_plan_golden_master_regression"
TEST_NODE = (
    "tests/test_frozen_sample_plan_golden_master_regression.py"
    "::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact"
)

_PRINT_RE = re.compile(
    r"PINNED_TERMINAL_NW\s*=\s*(?P<nw>-?\d+(?:\.\d+)?)\s*\n"
    r"PINNED_LIFETIME_TAX\s*=\s*(?P<tax>-?\d+(?:\.\d+)?)",
)
PROVENANCE_RE = re.compile(
    r"^# (?P<date>\d{4}-\d{2}-\d{2}): "
    r"PINNED_TERMINAL_NW=(?P<nw>-?\d+(?:\.\d+)?) "
    r"PINNED_LIFETIME_TAX=(?P<tax>-?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)
CONST_NW_RE = re.compile(r"^PINNED_TERMINAL_NW\s*=\s*(-?\d+(?:\.\d+)?)", re.MULTILINE)
CONST_TAX_RE = re.compile(r"^PINNED_LIFETIME_TAX\s*=\s*(-?\d+(?:\.\d+)?)", re.MULTILINE)

# Exact-match set: rejects a reason that IS one of these, verbatim (a short,
# generic non-answer). Deliberately does NOT include words common in honest
# prose ("fix", "update", "test", "regen", "changed") -- those are only
# rejected below if the ENTIRE reason is just that word, never as a
# substring, so "Recomputed after the DAF carryforward fix landed; see
# commit abc123" is never flagged for containing "fix".
_PLACEHOLDER_REASONS = {
    "todo", "tbd", "n/a", "na", "reason", "test", "testing", "placeholder",
    "asdf", "wip", "fix", "update", "regen", "update pin", "changed",
}
# Substring markers: unambiguous placeholder tokens that essentially never
# appear in a genuine justification, so they're caught anywhere in the text
# (word-boundary matched, case-insensitive) -- not just as the whole reason.
# This is what catches "TODO -- will fill in later, need more analysis time":
# long enough and not a whole-string match against _PLACEHOLDER_REASONS, but
# still a placeholder in substance (fix round 1, Finding 5).
_PLACEHOLDER_MARKERS = ("todo", "tbd", "fixme", "xxx", "placeholder", "wip", "n/a")
_PLACEHOLDER_MARKER_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in _PLACEHOLDER_MARKERS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)
MIN_REASON_LEN = 30


def _env_with_frozen_pricing():
    env = dict(os.environ)
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    return env


def _regen_interpreter() -> list[str]:
    """Argv prefix for running the regen block.

    Prefers the Windows launcher (`py -3.14`), which is what this repo's
    documented workflow calls for and what pins the interpreter version on a
    developer machine. Falls back to the interpreter running this tool when
    `py` is not on PATH -- otherwise the regen path this repo *mandates*
    (`CLAUDE.md`: hand-editing the pins is caught by
    `tests/test_golden_master_pin_provenance.py`) is simply unrunnable on
    Linux and CI, which is where it was first needed.

    Overridable via `RETIREMENT_SYSTEM_REGEN_PYTHON` for a machine with
    several interpreters and no launcher.
    """
    override = os.environ.get("RETIREMENT_SYSTEM_REGEN_PYTHON", "").strip()
    if override:
        return shlex.split(override)
    if shutil.which("py"):
        return ["py", "-3.14"]
    return [sys.executable]


def _run_regen_block(cwd: Path) -> tuple[float, float]:
    """Run the test file's own __main__ regen block and parse its output.

    This is the ONLY place a value is ever computed. Every subcommand below
    that needs a number calls this, never a hand-rolled reimplementation.
    """
    proc = subprocess.run(
        [*_regen_interpreter(), "-m", REGEN_MODULE],
        cwd=str(cwd),
        env=_env_with_frozen_pricing(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"Regen block failed at {cwd} (exit {proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    m = _PRINT_RE.search(proc.stdout)
    if not m:
        raise SystemExit(
            f"Could not parse regen block output at {cwd}:\n{proc.stdout}"
        )
    return float(m["nw"]), float(m["tax"])


def _current_pins() -> tuple[float, float]:
    text = PIN_FILE.read_text(encoding="utf-8")
    nw = CONST_NW_RE.search(text)
    tax = CONST_TAX_RE.search(text)
    if not nw or not tax:
        raise SystemExit(f"Could not locate PINNED_* constants in {PIN_FILE}")
    return float(nw.group(1)), float(tax.group(1))


def cmd_measure(_args) -> int:
    computed_nw, computed_tax = _run_regen_block(ROOT)
    pinned_nw, pinned_tax = _current_pins()
    print(f"Computed: terminal_nw={computed_nw:,.2f}  lifetime_tax={computed_tax:,.2f}")
    print(f"Pinned:   terminal_nw={pinned_nw:,.2f}  lifetime_tax={pinned_tax:,.2f}")
    d_nw = computed_nw - pinned_nw
    d_tax = computed_tax - pinned_tax
    print(f"Delta:    terminal_nw={d_nw:+,.2f}  lifetime_tax={d_tax:+,.2f}")
    if d_nw == 0 and d_tax == 0:
        print("MATCH -- the pin holds at the current worktree state.")
    else:
        print("MISMATCH -- the pin does not hold at the current worktree state.")
    return 0


def _git_status_porcelain() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT),
        capture_output=True, text=True, check=True,
    ).stdout


def cmd_verify_endpoint(args) -> int:
    status = _git_status_porcelain()
    if status.strip():
        print(
            "Refusing: working tree is dirty. verify-endpoint checks out a "
            "detached worktree at <sha> and must measure that commit's code "
            "exactly -- a dirty tree makes it ambiguous whether a result "
            "reflects the sha or your uncommitted changes.\n\n"
            + status,
            file=sys.stderr,
        )
        return 2

    sha = args.sha
    worktree_dir = Path(tempfile.mkdtemp(prefix="gm_verify_endpoint_"))
    # git worktree add refuses to create into a pre-existing non-empty dir;
    # mkdtemp already created it, so remove it and let git create it fresh.
    worktree_dir.rmdir()
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree_dir), sha],
            cwd=str(ROOT), check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"git worktree add failed:\n{exc.stdout}\n{exc.stderr}", file=sys.stderr)
        return 2

    try:
        proc = subprocess.run(
            ["py", "-3.14", "-m", "pytest", TEST_NODE, "-q", "-p", "no:randomly"],
            cwd=str(worktree_dir),
            env=_env_with_frozen_pricing(),
            capture_output=True, text=True, timeout=600,
        )
        print(proc.stdout)
        print(proc.stderr)
        if proc.returncode == 0:
            print(f"PIN HELD at {sha}: the frozen golden-master test passed at this commit.")
        else:
            print(
                f"PIN DID NOT HOLD at {sha}: the frozen golden-master test failed at this "
                "commit. Do not use this commit as a bisect 'good' endpoint -- see trap #1 "
                "in documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md."
            )
        return proc.returncode
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_dir)],
            cwd=str(ROOT), capture_output=True, text=True,
        )


def cmd_origin(args) -> int:
    value = args.value
    rel_path = PIN_FILE.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["git", "log", "--follow", f"-S{value}", "--oneline", "--date=short",
         "--pretty=format:%h %ad %s", "--", rel_path],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    )
    print(f"git log --follow -S{value} -- {rel_path}")
    print(
        "(--follow is required: a plain `git log -S` can name the wrong origin "
        "commit when a file rename makes the value look newly added -- trap #2 "
        "in documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md.)\n"
    )
    if not proc.stdout.strip():
        print("No candidates found.")
        return 1
    print(proc.stdout)
    return 0


def _validate_reason(reason_path: Path) -> str:
    if not reason_path.is_file():
        raise SystemExit(f"--reason file not found: {reason_path}")
    text = reason_path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"--reason file {reason_path} is empty. A pin cannot move silently.")
    if len(text) < MIN_REASON_LEN:
        raise SystemExit(
            f"--reason file {reason_path} is only {len(text)} chars (minimum "
            f"{MIN_REASON_LEN}). Explain what changed and why, not just that it did."
        )
    if text.strip().lower().rstrip(".!") in _PLACEHOLDER_REASONS:
        raise SystemExit(
            f"--reason file {reason_path} looks like a placeholder ('{text.strip()}'). "
            "Write an actual justification."
        )
    marker_match = _PLACEHOLDER_MARKER_RE.search(text)
    if marker_match:
        raise SystemExit(
            f"--reason file {reason_path} contains the placeholder marker "
            f"'{marker_match.group(0)}' ('{text.strip()}'). A reason that is long enough and "
            "not an exact placeholder can still just be a placeholder wearing more words -- "
            "write an actual justification, not a promise to write one later."
        )
    return text


def cmd_regen(args) -> int:
    if not args.reason:
        raise SystemExit("regen requires --reason <file>. A pin cannot move silently.")
    reason_path = Path(args.reason)
    reason_text = _validate_reason(reason_path)

    status = _git_status_porcelain()
    if status.strip():
        raise SystemExit(
            "Refusing: working tree is dirty. regen rewrites two tracked files "
            f"({PIN_FILE.relative_to(ROOT)}, {CHANGELOG_FILE.relative_to(ROOT)}) and needs a "
            "clean baseline to do that against -- a dirty tree makes it ambiguous whether the "
            "resulting diff reflects only the regen or also your uncommitted changes. Commit "
            "or stash first (consistent with verify-endpoint's same guard).\n\n" + status
        )

    old_nw, old_tax = _current_pins()
    new_nw, new_tax = _run_regen_block(ROOT)

    today = _dt.date.today().isoformat()
    pin_text = PIN_FILE.read_text(encoding="utf-8")

    provenance_line = (
        f"# {today}: PINNED_TERMINAL_NW={new_nw:.2f} PINNED_LIFETIME_TAX={new_tax:.2f}"
    )
    if PROVENANCE_RE.search(pin_text):
        pin_text = PROVENANCE_RE.sub(lambda _m: provenance_line, pin_text, count=1)
    else:
        pin_text = CONST_NW_RE.sub(
            lambda m: provenance_line + "\n" + m.group(0), pin_text, count=1
        )

    # Same format as the provenance line above (":.2f") -- not the constant's
    # own repr. They're only equivalent today because upstream values happen
    # to be pre-rounded to the cent; a single format keeps that guaranteed
    # rather than incidental, and keeps a future reader from suspecting two
    # different numeric sources when they're one (fix round 1, Finding 4).
    pin_text = CONST_NW_RE.sub(f"PINNED_TERMINAL_NW = {new_nw:.2f}", pin_text, count=1)
    pin_text = CONST_TAX_RE.sub(f"PINNED_LIFETIME_TAX = {new_tax:.2f}", pin_text, count=1)
    PIN_FILE.write_text(pin_text, encoding="utf-8")

    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    entry = (
        f"## {today} — Golden-master pin regenerated via `tools/regen_golden_master.py regen`\n\n"
        # Machine-readable binding required by
        # tests/test_golden_master_pin_provenance.py. Plain-float format (not
        # comma-grouped) so the gate parses it with float() directly. Prose
        # restating pin values deliberately does NOT satisfy that gate, because
        # entries about unrelated work routinely restate unchanged pins -- so
        # this marker is what makes a real regeneration distinguishable.
        f"<!-- pin-provenance: terminal_nw={new_nw:.2f} lifetime_tax={new_tax:.2f} -->\n\n"
        f"**Old pins.** terminal_nw={old_nw:,.2f}, lifetime_tax={old_tax:,.2f}\n\n"
        f"**New pins.** terminal_nw={new_nw:,.2f}, lifetime_tax={new_tax:,.2f}\n\n"
        f"**Reason.**\n\n{reason_text}\n\n"
    )
    CHANGELOG_FILE.write_text(entry + changelog, encoding="utf-8")

    print(f"Updated {PIN_FILE}")
    print(f"  PINNED_TERMINAL_NW: {old_nw:,.2f} -> {new_nw:,.2f}")
    print(f"  PINNED_LIFETIME_TAX: {old_tax:,.2f} -> {new_tax:,.2f}")
    print(f"Prepended dated entry to {CHANGELOG_FILE}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("measure", help="Print current computed values and delta vs. pins.").set_defaults(func=cmd_measure)

    p_verify = sub.add_parser(
        "verify-endpoint",
        help="Check out <sha> in a detached worktree and report whether the pin held there.",
    )
    p_verify.add_argument("sha")
    p_verify.set_defaults(func=cmd_verify_endpoint)

    p_origin = sub.add_parser(
        "origin", help="Run `git log --follow -S<value>` on the pin file."
    )
    p_origin.add_argument("value")
    p_origin.set_defaults(func=cmd_origin)

    p_regen = sub.add_parser(
        "regen", help="Rewrite the pins and append a changelog entry. Requires --reason."
    )
    p_regen.add_argument("--reason", required=False, help="Path to a file with the justification.")
    p_regen.set_defaults(func=cmd_regen)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
