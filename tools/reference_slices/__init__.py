"""Slice builders for ``tools/build_reference_db.py`` (dev-only; WP3).

Each slice is a module ``tools/reference_slices/<slice>.py`` with:

- ``SOURCES``: the files under ``reference_src/`` the slice owns (every file there
  must be owned by exactly one slice, or the build fails).
- ``build(src: Path) -> {table: (columns, rows)}``: parse those sources into
  typed rows (``None``/``int``/``float``/``str`` cells). Put an integer ``seq``
  column first when the getter needs source order; the build sorts every table.

Why here and not under ``src/``: builders read CSV/JSON source files, which the
shipped runtime must never do (the static file-I/O ratchet scans ``src/`` only),
and ``reference_src/`` is not bundled. The runtime half of a slice is its getter
in ``src/stores/ref_getters/<slice>.py``.

Register a new slice by appending its module name to ``SLICES``.
"""
SLICES: tuple[str, ...] = (
    "state_tax",
    "tax_law",
    "tax_update_dashboard",
)
