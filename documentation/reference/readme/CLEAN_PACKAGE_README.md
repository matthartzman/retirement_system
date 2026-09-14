# Clean Package Notes

This workspace is organized for single-machine desktop use. Top-level files are
kept intentionally sparse; project documentation lives under `documentation/`,
source code under `src/`, and browser assets under `frontend/`.

Generated folders such as `build/`, `dist/`, `__pycache__/`, and
`.pytest_cache/` can be recreated and should not be treated as source files.

Clean distributable zips built by `tools/build_release_package.py` intentionally
exclude local user/runtime folders: `.claude/`, `data/`, `input/`,
`local_state/`, `output/`, and `saved_plans/`. Users load or create Plan Data at
runtime; generated report outputs are rebuilt locally.
