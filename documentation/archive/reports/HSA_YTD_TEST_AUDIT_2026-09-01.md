# HSA/YTD Test-Cluster Duplication Audit — 2026-09-01

Wave 3 item 3.14 (system review 2026-08-31, finding Q9): "HSA and YTD test
clusters resemble the admin/roth pattern but were not confirmed duplicative
in this pass... schedule as a fast follow-up using the same method. Do not
act without first confirming actual duplication."

## Method

Same method used to confirm the admin/roth cluster (Q1/Q2, resolved in
Wave 1 item 1.14): for every file in the cluster, compare (a) each file's
own stated purpose (docstring / design doc reference), (b) test function
names for exact duplicates, and (c) literal string/assertion overlap
between file pairs, looking specifically for the admin/roth signature —
multiple files re-reading the same source artifact and asserting
overlapping facts about the same lineage, with no differentiation beyond
which layer/refactor introduced the literal.

## Scope

13 HSA files (`tests/test_hsa_*.py` plus
`test_contingent_liability_hsa_funding_regression.py` and
`test_workspace_isolated_holdings_hsa_liabilities_regression.py`, both of
which touch HSA behavior) and 6 YTD files
(`tests/test_ytd_*.py`) — 19 files, 3,936 lines total.

## Findings

**No confirmed duplication.** Unlike the admin/roth cluster:

- Every file's docstring names a distinct bug, ticket, or design spec
  (e.g. default-schedule fallback, medical-expense double-dip, optimizer
  H0-H5 wiring, the optimizer's consume-by-deadline risk dial, the
  schedule-override CSV contract, workspace-isolation of the schedule
  file, YTD header-tolerance ticket #279, YTD tax/growth rules). None
  documents itself as superseding or re-asserting another file's already-
  covered lineage, the tell that flagged the admin/roth cluster (one of
  those eight files explicitly documented a prior byte-identical
  removal).
- No two files in either cluster share a test function name.
- String-literal overlap between file pairs is present but incidental:
  shared config field names (`hsa_schedule_by_year`,
  `roth_heir_filing_status`), shared CSV fixture headers/paths
  (`client_hsa_schedule.csv`, `ytd_account_setup.csv`), and shared CSS/
  source-file path strings — the ordinary result of neighboring tests
  exercising related fixtures, not two files asserting the same fact for
  the same reason. The largest overlap (`test_ytd_levers_dashboard_functional.py`
  vs. `test_ytd_spending_growth_functional.py`, 10 shared literals) is
  fixture field-name overlap between a UI-wiring test and a tax/growth-
  calculation test — different subjects, incidental shared vocabulary.

## Conclusion

Per Q9's own instruction ("do not act without first confirming actual
duplication"), no merge is warranted. This audit report is the full
deliverable for item 3.14.
