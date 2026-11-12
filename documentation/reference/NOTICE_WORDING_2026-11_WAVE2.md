# Limitation notice wording N8 and N10 (System Review 2026-11-10, W2-03)

Status: draft. Wording is proposed by the engine maintainer and still needs the financial planner's wording review (FIN-001, FIN-005). N9 (FIN-004, Illinois estate tax) was removed in W4-01 once the attorney confirmed the method; its id is not reused. Companion to `documentation/archive/reports/SYSTEM_REVIEW_2026-10-19_WAVE1_NOTICE_WORDING.md` (N1-N7). Notices change no calculation. The registry is `src/limitation_notices.py`; a test compares the text below with it.

| ID | Finding | Severity | Shown when | Removed when |
|---|---|---|---|---|
| N8 | FIN-001 | warning | QBI is switched on and the plan has an S-corp or sole-proprietor business | W3-02 follow-up: CPA confirms specified-service status and the plan gains screens for it (limits themselves modeled in W3-02, 2026-11-11) |
| N10 | FIN-005 | info | The Existing Life Insurance module has at least one policy | W4-04: policy proceeds are integrated into the projection and estate base |

**N8.** The qualified business income (QBI) deduction applies the income-threshold phase-in, the W-2 wage limit, the taxable-income cap and the 2026 minimum deduction, but treats the business as one business whose specified-service status and qualified property come from Plan Data (Cashflow, Self-Employment: qbi_sstb and qbi_ubia; the defaults are not a specified service business and no property). If your business is a specified service business (for example consulting, law, accounting or health), set qbi_sstb to TRUE: otherwise the deduction is overstated above the income threshold. Capital gains from withdrawals are not netted in the taxable-income cap. Ask a tax professional to confirm your status.

**N10.** Life insurance policies entered in Plan Data are an inventory only. A death in the projection does not pay a death benefit to the survivor, and policy proceeds are not added to the estate tax calculation. Whether proceeds are part of a taxable estate depends on who owns and controls the policy; this plan does not decide that.

## Status of N8's removal condition (2026-11-12)

N8's removal condition has two parts: the CPA confirms specified-service status, and the plan gains screens for it. The first part is met (register row A1, confirmed 2026-11-11: the household is a specified service business). The notice stays, because `qbi_sstb` is still unset in the live plan (the default is FALSE), so the engine still treats the business as not specified-service. Setting the field is step 4 of the register's next steps (section F). Remove or reword N8 only after the field is set in the live plan; that was not checked here against the live file (real data), so confirm it when you set the field.

## Notes

- N10 is worded so it does not imply that every policy outside an irrevocable life insurance trust is in the estate (inclusion follows ownership and control, IRC 2042).
