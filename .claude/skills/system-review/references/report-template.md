# Final Report Template

The generated Markdown report must contain:

1. Executive summary — assessment, risks/opportunities, planner verdict, recommendations.
2. Scope and methodology — scope, date, depth, roles, model tiers, phases, GitHub repository/ref/commit/PR context, relevant issues/PRs, runtime-validation status, and the explicit CI exclusion.
3. Coverage matrix — area, status, evidence, expert, findings, residual uncertainty.
4. System health assessment — architecture, usability/accessibility, documentation, quality/testing, financial correctness, data integrity, security/privacy, and performance. Do not include CI health.
5. Material findings — all required finding fields; no CI findings.
6. Options and tradeoffs.
7. Recommendation.
8. Target design — boundaries, responsibilities, shared code, data/calculation flows, UI, validation, errors, persistence, tests, docs, assumptions, migrations as applicable.
9. Implementation waves — dependency-ordered and genuinely parallelizable work; no CI remediation tasks.
10. Validation plan — item-level validation plus system acceptance criteria; no CI validation claims.
11. Assumptions and open questions — technical, jurisdiction/rule-year, external facts, professional-review needs.
12. Review limitations — uninspected areas, unavailable evidence, runtime/external limitations, and `CI was intentionally excluded from this review.`
13. Finding disposition appendix — refuted, duplicate, superseded, insufficient-evidence material items and reasons.
14. Financial planner sign-off — verdict, requested changes, resolution, impact analysis, dissent.

The coverage matrix or associated appendix must identify relevant GitHub issues, pull requests, and flagged/pending work inspected, including final disposition.

## Report quality gate

Before finalization confirm that evidence was actually inspected; uninspected areas are not called healthy; High/Critical findings are dispositioned; target design/waves/recommendation agree; material work has validation and exit criteria; financial claims are bounded by jurisdiction/rule-year uncertainty; runtime claims are truthful; and CI is excluded throughout.