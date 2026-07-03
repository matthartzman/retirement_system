# Release notes

Per-release notes for this application live in this directory, one file per
release (e.g. `RELEASE_NOTES_v10.1.md`), instead of at the project root.
`tests/test_12_package_consolidation.py::test_release_notes_are_under_documentation_release_notes`
enforces both halves of this: no `RELEASE_NOTES*.md` at the project root, and
this directory must exist.
