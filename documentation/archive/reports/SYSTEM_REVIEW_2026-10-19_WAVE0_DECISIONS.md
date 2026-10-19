# System Review 2026-10-19 — Wave 0 Decision Record

Companion to `SYSTEM_REVIEW_2026-10-19.md` (section 9, Wave 0). Decisions recorded 2026-10-19 by the repository owner. No code changed. CI was intentionally excluded from the review.

## WI-001 — Trends-log backup (QA-001)

| Item | Decision |
|---|---|
| Remote visibility | Public |
| Clone/fork list | Owner verified (2026-10-19) that no clones or forks exist outside the owner's own copies |
| Chosen option | Purge history (git filter-repo, then force-push) after the HEAD fix |
| Follow-up | A separate scheduled task is required for the purge; with no external clones, no clone-notification step is needed beyond the owner's own copies, which must be re-cloned or reset after the force-push. Before purging, the owner reviews which account labels and balances the file holds and decides whether anything needs rotating or renaming. Never copy values from the file into any document. |

Exit criteria met: decision recorded. Purge itself is not scheduled yet (see open items).

## WI-002 — Scope and policy

| Item | Decision | Professional review |
|---|---|---|
| (a) Retiring before 59.5 (FIN-004) | In scope: model the 10% additional tax and its IRC 72(t) exceptions | CPA for the exceptions |
| (b) Earnings test (FIN-007) | In scope. Owner reviewed `income.py:322-396` on 2026-10-19 and confirmed the earnings test is missing; FIN-007 moves from insufficient_evidence to confirmed (owner-verified) | Benefits counselor or CPA |
| (c) Brokerage-gain MAGI phasing (FIN-001) | Two phases. Phase 1: IRMAA MAGI only, pinned separately. Phase 2: NIIT, ACA MAGI and Social Security taxation | Planner sign-off before each golden re-pin; CPA review recommended for phase 2 |
| (d) Monte Carlo headline (FIN-002) | "Funded as asked". The secondary "without using Roth for extras" figure is removed from the tile | Planner reviews the displayed success definition |
| (e) Federal estate defaults (FIN-009) | Derive the exemption from the household: single exemption for one-person households; married default only for couples with a portability election | Estate attorney |

Jurisdiction for all items: US federal (state rows are covered by WI-003). Rule year: statutory structure, with 2026 parameters from the dataset.

## WI-003 — External rule-value verification

Status: verified by the owner acting as advisor (2026-10-19), covering the checklist below. The per-row table of value, source citation and retrieval date was not supplied, so this record states the outcome only. Add the table here if it is needed for audit, and mark any row not individually verified as unverified.

- 2026 AMT exemption, phase-out start and rate (FIN-005)
- 2026 QLAC and QCD limits (FIN-011)
- NC, IN, CA and NY state rows, NY estate exemption (FIN-006)
- Part D base premium and Social Security wage-base status (FIN-006)
- SSA mortality table (FIN-006)
- Federal estate exemption and portability treatment (FIN-009)
- Current ACA enhanced-subsidy law

The estate-attorney review for FIN-009 portability and credit-shelter arithmetic is a separate requirement and is not covered by this verification.

## Other owner decisions (from the section 11 open questions)

- Monarch may be named in the README and UI; describe extraction as vendor-neutral, since more integrations are planned.
- Hosted use is planned: ARC-001 and ARC-009 (authentication, Host allow-list, remove `ALLOW_UNAUTHENTICATED_SAAS=YES`, non-loopback startup guard) are required before any hosted deployment.

## Purge status check (2026-10-19)

The owner stated a history purge was done "as of 10/1/2026". A repository check does not support that for this file: `financial_trends_log.jsonl.bak` was added in commit 0bd50f3 (#215, committed 2026-10-14, after 10/1), is still tracked at HEAD, and is still in history on `main`. An earlier purge cannot have covered a file added later. Any 10/1 purge, if done, was of other content or a different copy. The QA-001 purge is therefore still open.

## Open items blocking Wave 1

1. Reconcile the purge status above, then run the QA-001 HEAD fix and, if still wanted, the history rewrite (needs explicit go-ahead before any force-push).
2. Optional: the per-row WI-003 verification table, if an audit trail is wanted.
