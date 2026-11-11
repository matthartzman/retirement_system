# Limitation notice wording N8-N10 (System Review 2026-11-10, W2-03)

Status: draft. Wording is proposed by the engine maintainer and still needs the financial planner's wording review (FIN-001, FIN-004, FIN-005); the Illinois figure also needs the estate attorney's confirmation. Companion to `documentation/archive/reports/SYSTEM_REVIEW_2026-10-19_WAVE1_NOTICE_WORDING.md` (N1-N7). Notices change no calculation. The registry is `src/limitation_notices.py`; a test compares the text below with it.

| ID | Finding | Severity | Shown when | Removed when |
|---|---|---|---|---|
| N8 | FIN-001 | warning | QBI is switched on and the plan has an S-corp or sole-proprietor business | W3-02 follow-up: CPA confirms specified-service status and the plan gains screens for it (limits themselves modeled in W3-02, 2026-11-11) |
| N9 | FIN-004 | warning | Resident state is Illinois and projected net worth exceeds the Illinois estate exclusion | W4-01: the estate attorney reviews the calculation and it is corrected |
| N10 | FIN-005 | info | The Existing Life Insurance module has at least one policy | W4-04: policy proceeds are integrated into the projection and estate base |

**N8.** The qualified business income (QBI) deduction applies the income-threshold phase-in, the W-2 wage limit, the taxable-income cap and the 2026 minimum deduction, but treats the business as one business whose specified-service status and qualified property come from Plan Data (Cashflow, Self-Employment: qbi_sstb and qbi_ubia; the defaults are not a specified service business and no property). If your business is a specified service business (for example consulting, law, accounting or health), set qbi_sstb to TRUE: otherwise the deduction is overstated above the income threshold. Capital gains from withdrawals are not netted in the taxable-income cap. Ask a tax professional to confirm your status.

**N9.** The Illinois estate tax figure is an approximation that has not been verified against the Illinois Attorney General's calculator. For estates just above the $4 million exclusion it may overstate the tax. It feeds the Post-Tax Inheritance figure, the Estate sheet and the Roth conversion rationale. Ask an estate attorney to confirm the figure before relying on it.

**N10.** Life insurance policies entered in Plan Data are an inventory only. A death in the projection does not pay a death benefit to the survivor, and policy proceeds are not added to the estate tax calculation. Whether proceeds are part of a taxable estate depends on who owns and controls the policy; this plan does not decide that.

## Notes

- N9 is shown whatever the estate objective mode: Post-Tax Inheritance and the Estate sheet use the Illinois figure in every mode, and the Roth strategy uses it unless `estate_tax_objective_mode` is OFF or MONITOR_ONLY.
- N10 is worded so it does not imply that every policy outside an irrevocable life insurance trust is in the estate (inclusion follows ownership and control, IRC 2042).
