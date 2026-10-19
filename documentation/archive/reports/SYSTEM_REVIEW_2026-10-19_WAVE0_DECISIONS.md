# System Review 2026-10-19 — Wave 0 Decision Record

Companion to `SYSTEM_REVIEW_2026-10-19.md` (section 9, Wave 0). Decisions recorded 2026-10-19 by the repository owner. No code changed. CI was intentionally excluded from the review.

## WI-001 — Trends-log backup (QA-001)

| Item | Decision |
|---|---|
| Remote visibility | Public |
| Clone/fork list | Not enumerated. Treat as unknown; any existing clone or fork keeps the old blob. |
| Chosen option | Purge history (git filter-repo, then force-push) after the HEAD fix |
| Follow-up | A separate scheduled task is required for the purge, with a clone-notification step. Before purging, the owner reviews which account labels and balances the file holds and decides whether anything needs rotating or renaming. Never copy values from the file into any document. |

Exit criteria met: decision recorded. Purge itself is not scheduled yet (see open items).

## WI-002 — Scope and policy

| Item | Decision | Professional review |
|---|---|---|
| (a) Retiring before 59.5 (FIN-004) | In scope: model the 10% additional tax and its IRC 72(t) exceptions | CPA for the exceptions |
| (b) Earnings test (FIN-007) | In scope. The claim is still unconfirmed: a verifier must open `income.py:322-396` before work starts | Benefits counselor or CPA |
| (c) Brokerage-gain MAGI phasing (FIN-001) | Two phases. Phase 1: IRMAA MAGI only, pinned separately. Phase 2: NIIT, ACA MAGI and Social Security taxation | Planner sign-off before each golden re-pin; CPA review recommended for phase 2 |
| (d) Monte Carlo headline (FIN-002) | "Funded as asked". The secondary "without using Roth for extras" figure is removed from the tile | Planner reviews the displayed success definition |
| (e) Federal estate defaults (FIN-009) | Derive the exemption from the household: single exemption for one-person households; married default only for couples with a portability election | Estate attorney |

Jurisdiction for all items: US federal (state rows are covered by WI-003). Rule year: statutory structure, with 2026 parameters from the dataset.

## WI-003 — External rule-value verification

Not decided; it needs a CPA or advisor and cannot be done in this review. Checklist to hand over (value, source citation, retrieval date and verifier are to be filled in per row):

- 2026 AMT exemption, phase-out start and rate (FIN-005)
- 2026 QLAC and QCD limits (FIN-011)
- NC, IN, CA and NY state rows, NY estate exemption (FIN-006)
- Part D base premium and Social Security wage-base status (FIN-006)
- SSA mortality table (FIN-006)
- Federal estate exemption and portability treatment (FIN-009)
- Current ACA enhanced-subsidy law

## Other owner decisions (from the section 11 open questions)

- Monarch may be named in the README and UI; describe extraction as vendor-neutral, since more integrations are planned.
- Hosted use is planned: ARC-001 and ARC-009 (authentication, Host allow-list, remove `ALLOW_UNAUTHENTICATED_SAAS=YES`, non-loopback startup guard) are required before any hosted deployment.

## Open items blocking Wave 1

1. WI-003 external verification has no owner or date.
2. The history purge needs a scheduled date and a list of known clones/forks.
3. FIN-007 needs a verifier to confirm the earnings test is actually missing.
