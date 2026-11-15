# macOS Port Plan

Status: draft
Date: 2026-11-15

## Goal and scope

Run the retirement planner on a Mac. This plan is based on a read-only code survey; nothing has been
run on a Mac yet. Phase 0 exists to confirm or correct the survey before any code changes.

Three target levels, each a stopping point:

| Level | Meaning | Phases |
|---|---|---|
| A | Runs from source in server mode, used in a browser | 0 |
| B | Native desktop window from source | 0-2 |
| C | Double-clickable `.app`, scheduled Monarch import, CI coverage | 0-6 |

Recommendation: do Phase 0 first, then decide between A, B and C with real evidence.

## What the survey found

Portable already:
- Core dependencies (numpy, scipy, lxml, openpyxl, keyring) are cross-platform; `src/` has no `msvcrt`,
  `winreg` or `pywin32` imports.
- `src/desktop_api.py:229` `_open_path` already branches `win32` / `darwin` / other.
- `src/platform_runtime.py:88` `frozen_workspace_root()` falls back to `~/.local/share/RetirementPlanner`.
- `src/onedrive_guard.py` already names iCloud among synced folders.
- `tools/launchers/start_ui.sh` and `START_UI.command` exist and call `START_DESKTOP.py`.

Windows-only:
- `src/desktop_app.py` (WebView2 comments; `private_mode=False`, `storage_path`) needs verifying under WKWebView.
- `retirement_planner.spec` (Windows onedir, `keyring.backends.Windows` hidden import); `build.py:49` already
  picks the exe name by platform.
- `src/monarch_autoupdate.py:306` (PowerShell and Task Scheduler) and `:330` (non-Windows early return);
  `src/monarch_autoimport_job.py:34` (looks for `.venv/Scripts/python.exe`).
- `Monarch Extractor/run_monarch.ps1`, `register_monarch_extract_task.ps1`, `tools/launchers/register_monarch_autoimport_task.ps1`.
- `launchers/*.bat`, `tools/INSTALL_DESKTOP_ICON.py` (PowerShell shortcut).
- Dev tooling: `tools/bump_version.py:528,662` (PowerShell, `DETACHED_PROCESS`), `tools/sync_main.ps1`.
- CI: every job in `.github/workflows/ci.yml` and `nightly.yml` runs on `windows-latest`.
- Tests: `tests/test_windows_console_encoding_regression.py`; static tests over the spec and the frozen secrets path.

## Phases

Each phase lists model/effort, a relative usage estimate (not a token count) and what drives it. Check
`/usage` against these as the plan executes.

### Phase 0 - Mac spike, no code changes (Level A)

On a Mac: install Python 3.14, create a venv, `pip install -r requirements.txt`, run
`tools/launchers/start_ui.sh` (desktop) and server mode on port 5050, run `pytest -m "not slow"` and
`npm test`. Record every failure in a list; this is the work estimate for the rest.
- Model/effort: Sonnet, low. Mostly the user running commands; Claude only triages the failure log.
- Usage: light. Driver: reading pytest logs (write them to a log file, per the project rule).
- Exit: a failure list classified as "Windows-only test", "real Mac bug" or "environment".

### Phase 1 - Desktop window on macOS (Level B)

- Add `pyobjc` (or pywebview's Cocoa extra) to requirements behind a `sys_platform == "darwin"` marker.
- Verify `webview.start(..., private_mode=False, storage_path=...)` persists localStorage under WKWebView; fix
  `src/desktop_app.py` if not. Check window sizing, file dialogs and the JS-to-Python bridge (`DesktopApi`).
- Check XLSX download/open via `open` (already coded) and keyring Keychain prompts.
- Model/effort: Sonnet, medium. Needs Mac iteration; debugging is trial-and-error on the user's machine.
- Usage: moderate. Driver: repeated launch-fix cycles; keep each cycle to one targeted file read.
- Risk: pywebview behavior differences are the biggest unknown; this phase can grow if the bridge misbehaves.

### Phase 2 - Per-user data location (Level B)

- In `frozen_workspace_root()` add a macOS branch: `~/Library/Application Support/RetirementPlanner`.
  Keep the Linux and Windows branches and add a test per branch.
- Update `tests/test_frozen_secrets_path_regression.py` expectations if they pin the fallback path.
- Model/effort: Sonnet, low. Small and well-bounded.
- Usage: light.

### Phase 3 - Packaged `.app` (Level C)

- `retirement_planner.spec`: add a `sys.platform == "darwin"` branch producing a `BUNDLE`, an `.icns` icon, and
  `keyring.backends.macOS` hidden import (drop the Windows backend there).
- Check `build.py` and `main.py` paths that assume an exe; confirm the subprocess build tests under the frozen layout.
- Build on a Mac (PyInstaller does not cross-build). Decide arm64-only vs universal2.
- Signing and notarization: needs an Apple Developer account (paid). Without it the app runs only after the user
  overrides Gatekeeper (right-click Open).
- Update `tests/test_frozen_build_spec_static_unit.py` for the new branch.
- Model/effort: Opus, medium for the spec design; Sonnet, medium for iteration.
- Usage: moderate to heavy. Driver: build-run-fix loops and long PyInstaller logs; read only the log tail.
- Disproportionate-cost flag: avoid full `pytest` after every spec tweak. Use the smoke script
  (`scripts/pyinstaller_smoke.py`) as the inner loop.

### Phase 4 - Monarch auto-import and extractor (Level C)

- Replace Task Scheduler with a per-user `launchd` agent (plist in `~/Library/LaunchAgents`) in
  `monarch_autoupdate.py`; keep the Windows path behind `sys.platform`.
- `monarch_autoimport_job.py:34`: look for `.venv/bin/python` as well as `Scripts/python.exe`.
- Port `run_monarch.ps1` and the register scripts to POSIX `sh`; confirm Playwright Chromium installs on macOS.
- Model/effort: Sonnet, medium. Opus not needed; the logic is a mapping of existing behavior.
- Usage: moderate. Driver: tests that mock `subprocess` around the scheduler; the real scheduler needs a Mac check.
- Optional: skip this phase entirely if Monarch import is run manually on the Mac.

### Phase 5 - Launchers and install experience (Level C)

- `.command` launchers for desktop and server (make executable; note the quarantine flag on downloaded files).
- Replace `INSTALL_DESKTOP_ICON.py` with a macOS flow (drag `.app` to Applications, or a Dock alias).
- Dev tooling only if developing on the Mac: make `bump_version.py` and `sync_main.ps1` calls platform-aware.
- Model/effort: Sonnet, low.
- Usage: light.

### Phase 6 - CI and tests (Level C)

- Add `macos-latest` to the `test` matrix in `ci.yml` (keep Windows). Mark Windows-only tests with `skipif`.
- Cost note: macOS runner minutes bill at a higher multiplier on private repos; start with the fast loop
  (`pytest -m "not slow"`) only and run the full suite nightly.
- Watch the repo ratchets: new test files need a type suffix and must not encode tracking ids; new `.md` under
  `documentation/future/` needs a `Status:` line (this file has one).
- Frontend line ceiling is untouched (no frontend changes planned).
- Model/effort: Sonnet, medium.
- Usage: moderate. Driver: CI log reading; pull failed-job logs by job, not whole runs.

### Phase 7 - Docs and gates

- Update `documentation/reference/CLAUDE.md` (run commands) and the design spec with macOS launch and data paths.
- Regenerate `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` if any file under `src/` moves or is added
  (`python tools/generate_system_diagram.py`), and run `python tools/fast_gates.py` before every push.
- Model/effort: Sonnet, low. Usage: light.

## Cross-cutting risks

- **Case sensitivity.** macOS defaults to case-insensitive APFS, Windows is case-insensitive, Linux is not. Low
  risk here, but a Phase 0 run will show it.
- **Line endings.** Repo stores LF; the Windows checkout is CRLF via `core.autocrlf`. A Mac checkout is LF,
  which matches the repo, so text-hygiene checks should be easier, not harder.
- **Golden masters.** Floating-point results can differ slightly between arm64 and x64 numpy builds. If
  `test_phase_golden_equality_regression` drifts on the Mac, run `tools/regen_golden_master.py measure` first and
  hand-verify one delta; never regenerate pins to make the Mac pass.
- **Sync folders.** If the repo lives in iCloud Drive, SQLite WAL files can corrupt; keep the workspace outside it.
- **Python 3.14 on macOS.** Confirm wheels exist for numpy, scipy and lxml on arm64 during Phase 0.

## Decisions needed from the owner

1. Which level (A, B or C) is the goal?
2. Is an Apple Developer account (paid) acceptable for signing and notarization, or is Gatekeeper override fine?
3. Apple Silicon only, or Intel too (universal2)?
4. Is scheduled Monarch import needed on the Mac, or is manual run enough?

## Rough effort

| Phase | Effort | Relative usage |
|---|---|---|
| 0 Spike | Under an hour | Light |
| 1 Desktop window | 0.5-1 day | Moderate |
| 2 Data path | 1-2 hours | Light |
| 3 `.app` packaging | 2-4 days | Moderate to heavy |
| 4 Monarch | 1-2 days | Moderate |
| 5 Launchers | 0.5 day | Light |
| 6 CI/tests | 1-2 days | Moderate |
| 7 Docs | 2-3 hours | Light |

Level B is roughly 1-2 days; Level C is roughly 1-2 weeks. All of it needs access to a Mac.
