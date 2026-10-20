# Retirement System Input Package: import/export format notes

This package is separate from the application package, which deliberately does
not include `input/`.

The app does not read these files while it runs. Your plan lives in the plan
file (`plan.rpx`) that the app keeps for you. The CSV files in `input/` are
sample and exchange files: you bring them in with an import, and the app writes
the same shapes out with an export.

Contents:

- `input/demo/`: a fictional household in CSV form (see `input/demo/README.md`).
- `input/ytd_transactions_sample.csv`: an example of the transaction import format
  (see `input/README_YTD_INPUTS.md`).

To bring a folder of CSV files into the app: **Settings -> Data & Maintenance ->
CSV backup -> Import from folder**. The app shows a preview first and changes
nothing until you confirm. **Export CSV backup** and **Export to folder** on the
same card write your plan out in the same format. Editing a CSV file left in
`input/` does not change your plan.

How rows map to the plan file: `documentation/reference/PLAN_ROWS_MODEL.md`.
