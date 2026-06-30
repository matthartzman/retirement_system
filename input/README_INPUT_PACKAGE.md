# Retirement System v8.3 Input Package

This package is intentionally separate from the clean application package.

Contents:

- `input/`: local/default Plan Data folder for desktop or local runs.
- `plan_data_manifest.json`: checksum manifest for the canonical CSV Plan Data files and synchronized JSON/YAML exports.
- `documentation/roadmap_implementation_validation.md`: validation notes retained for traceability.

To use locally, extract this zip next to the application package and select or copy the desired Plan Data folder through the UI/server configuration. The clean application package deliberately does not include `input/`.
