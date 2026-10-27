# Release Notes

Versioned release notes for the Retirement Planning system live in this
directory, one file per release (for example `v11.0.0.md`; today's files are dated, such as `2026-09-changes-334-339.md`). Keeping them here
matches the repository's documentation layout — long-form docs under
`documentation/`, READMEs under `documentation/reference/readme/`, and release notes under
`documentation/reference/release_notes/` — and keeps the project root free of
`RELEASE_NOTES*.md` files.

`tests/test_package_consolidation_functional.py::test_release_notes_are_under_documentation_release_notes`
enforces both halves of this: no `RELEASE_NOTES*.md` at the project root, and
this directory must exist.

Entries:

- [`2026-09-changes-334-339.md`](2026-09-changes-334-339.md) -- IRMAA indexing (#334), one-time Large Discretionary (#336), Next Housing Move gating (#338) and related changes.
- [`2026-10-monarch-balances-and-reconciliation.md`](2026-10-monarch-balances-and-reconciliation.md) -- daily Monarch account balances, the trends charts built on them, and the Monarch Reconciliation page.
- [`2026-10-monarch-mapping-and-trends-fixes.md`](2026-10-monarch-mapping-and-trends-fixes.md) -- Monarch mapping redesign (inbox, policies, closed accounts, automatic updates) and the Financial Reporting fixes (items 349 to 354).
- [`2026-10-trends-live-snapshot.md`](2026-10-trends-live-snapshot.md) -- Financial Trends Live Snapshot: live holdings valuation, returns net of new money, estimated tax and after-tax net worth.
- [`2026-10-wp11-file-elimination.md`](2026-10-wp11-file-elimination.md) -- WP11 storage changes: where plan data, settings and secrets live now, and CSV as import/export only.

- [`2026-10-engine-tax-correctness.md`](2026-10-engine-tax-correctness.md) -- October tax-correctness engine changes: senior bonus for itemizers, qualified-dividend stacking, brokerage and home/rental sale gains in income tests, symmetric survivor step-up, the rental and housing changes (H2 to H6), and the September engine changes.

## Golden-master changelog map

Every `GOLDEN_MASTER_CHANGELOG.md` entry dated 2026-09 or later maps to a note
below, or is explicitly marked "no user-visible change".

| Changelog entry | Note |
|---|---|
| 2026-10-20 WI-023b Roth LTCG cap basis | `2026-10-engine-tax-correctness.md` |
| 2026-10-20 pin regen (WI-024 phase 2: NIIT, ACA, Social Security) | `2026-10-engine-tax-correctness.md` |
| 2026-10-20 WI-024 phase 1 (IRMAA MAGI) | `2026-10-engine-tax-correctness.md` |
| 2026-10-20 pin regen (WI-023 qualified-dividend stacking; WI-025 step-up) | `2026-10-engine-tax-correctness.md` |
| 2026-10-19 pin regen (senior bonus for itemizers) | `2026-10-engine-tax-correctness.md` |
| 2026-10-13 H1 sale gains in AGI | `2026-10-engine-tax-correctness.md` |
| 2026-10-03, 10-02 (x2), 10-01 `conv_guardrail_caps` snapshots | No user-visible change (test fixture diagnostics only) |
| 2026-09-30 fixture provenance binding | No user-visible change (test tooling) |
| 2026-09-29 pin regens: 2026-tax-rows (WI-301), WI-310, WI-303, IRMAA tier-4 correction; WI-304 IRMAA lookback | `2026-10-engine-tax-correctness.md` (September table) |
| 2026-09-28 pin regen (WI-105) and WI-103/104 survivor entry | `2026-10-engine-tax-correctness.md` (September table) |
| 2026-09-24 IRMAA indexing and CMS table correction (#334), repin correction | `2026-09-changes-334-339.md` |
| 2026-09-08, 2026-09-04 pin regens (Social Security / annuity arrears proration) | `2026-10-engine-tax-correctness.md` (September table) |
| 2026-09-02 Ticket 305 `Monarch Id` column | No user-visible change (additive column; see `2026-10-monarch-mapping-and-trends-fixes.md` for the Monarch feature) |

For the running record of golden-master projection changes, see
[`../GOLDEN_MASTER_CHANGELOG.md`](../GOLDEN_MASTER_CHANGELOG.md).
