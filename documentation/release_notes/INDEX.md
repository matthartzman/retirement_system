# Release Notes

Versioned release notes for the Retirement Planning system live in this
directory, one file per release (for example `v10.0.0.md`). Keeping them here
matches the repository's documentation layout — long-form docs under
`documentation/`, READMEs under `documentation/readme/`, and release notes under
`documentation/release_notes/` — and keeps the project root free of
`RELEASE_NOTES*.md` files.

`tests/test_12_package_consolidation.py::test_release_notes_are_under_documentation_release_notes`
enforces both halves of this: no `RELEASE_NOTES*.md` at the project root, and
this directory must exist.

For the running record of golden-master projection changes, see
[`../GOLDEN_MASTER_CHANGELOG.md`](../GOLDEN_MASTER_CHANGELOG.md).
