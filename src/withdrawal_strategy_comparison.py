from __future__ import annotations
"""Named withdrawal-sequencing strategy comparison.

System review finding withdrawal-sequencing-not-comparable (planner, 5.2):
the deterministic engine's real withdrawal cascade (HSA -> pretax elective
-> taxable trust -> Roth-last) is a single hardcoded sequence, with a
multi-round tax true-up (ordinary income, then LTCG/NIIT) written assuming
that exact order. Genuinely offering "named strategies" the engine itself
executes would mean re-deriving that true-up math for every possible
account order -- IRMAA/NIIT/LTCG bracket thresholds interact differently
depending on which income type stacks on which. That is real engine-rewrite
risk for a comparison feature, not a bug fix.

This module answers the planner's actual question -- "how would spending
from these accounts in a different order compare?" -- as a deliberately
separate, lower-fidelity tool instead: it reuses the REAL plan's own
already-computed year-by-year numbers for RMDs (forced regardless of
strategy) and the REAL total elective withdrawal need (trust_wd + hsa_wd +
roth_wd + ira_wd, i.e. what has to come from discretionary accounts beyond
RMDs), and only varies WHICH accounts fund that already-known need under
each named strategy, using a simplified flat-rate tax treatment (the
household's own marginal rate for ordinary income, a flat LTCG rate for
taxable-account gains, no tax on Roth). It does not reproduce IRMAA
cliffs, NIIT, or bracket-filling precision -- see the "approximate" labeling
on every consumer of this module's output.
"""
from typing import Any, Mapping

from . import core as _ar
from .core import marginal_rate

# Two illustrative strategies plus the household's own current plan, in the
# order each searches for a discretionary-need dollar. RMDs are pulled from
# pretax regardless of strategy (they are statutorily forced, not a choice).
WITHDRAWAL_STRATEGIES = {
    "current_plan": {
        "label": "Current Plan (HSA → Pre-Tax → Taxable → Roth-Last)",
        "order": ["hsa", "pretax", "taxable", "roth"],
        "description": "Approximates this plan's actual engine-computed sequence: HSA for wellness costs, "
                        "then pre-tax elective withdrawals, then the taxable/trust account, with Roth spent only "
                        "as a last resort so it compounds tax-free the longest.",
    },
    "conventional_taxable_first": {
        "label": "Conventional (Taxable → Pre-Tax → Roth)",
        "order": ["hsa", "taxable", "pretax", "roth"],
        "description": "The textbook default: spend the taxable/trust account first so tax-advantaged accounts "
                        "keep compounding, then pre-tax, then Roth.",
    },
    "proportional": {
        "label": "Proportional (Draw From All Three by Balance Share)",
        "order": "proportional",
        "description": "Draws from pre-tax, taxable, and Roth each year in proportion to their current balances, "
                        "rather than fully depleting one account type before touching the next.",
    },
    "roth_first": {
        "label": "Roth-First (Spend Tax-Free Assets Early)",
        "order": ["hsa", "roth", "taxable", "pretax"],
        "description": "Spends Roth first. Rarely tax-optimal -- included as a comparison baseline showing the "
                        "cost of giving up Roth's tax-free compounding early, e.g. for clients prioritizing "
                        "simplicity or averse to future RMDs on a large remaining balance.",
    },
}


def _account_ids_by_bucket(c: Mapping[str, Any]) -> dict:
    return {
        "pretax": set(c.get("pre_tax_ids") or _ar.ids_by_tax(c.get("account_registry") or {}, "pre_tax")),
        "roth": set(c.get("roth_ids") or _ar.ids_by_tax(c.get("account_registry") or {}, "roth")),
        "taxable": set(c.get("taxable_ids") or _ar.taxable_ids(c.get("account_registry") or {})),
    }


def _starting_balances_by_type(c: Mapping[str, Any]) -> dict:
    balances = c.get("balances") or {}
    ids_by_bucket = _account_ids_by_bucket(c)
    return {bucket: sum(float(balances.get(a, 0.0) or 0.0) for a in ids) for bucket, ids in ids_by_bucket.items()}


def _bucket_growth_rates(c: Mapping[str, Any]) -> dict:
    """Balance-weighted average growth rate per bucket, from the same
    per-account account_returns Wave 3.5 populates (asset location matters:
    a bond-heavy pre-tax account and an equity-heavy Roth do not compound at
    the same rate). Falls back to the flat c['ret'] for any bucket with no
    account_returns entries, so this degrades gracefully rather than
    silently using 0.0 if that population ever fails."""
    base_ret = float(c.get("ret", 0.06) or 0.06)
    balances = c.get("balances") or {}
    account_returns = c.get("account_returns") or {}
    ids_by_bucket = _account_ids_by_bucket(c)
    rates = {}
    for bucket, ids in ids_by_bucket.items():
        total = sum(float(balances.get(a, 0.0) or 0.0) for a in ids if a in account_returns)
        if total <= 0:
            rates[bucket] = base_ret
            continue
        weighted = sum(float(balances.get(a, 0.0) or 0.0) * float(account_returns.get(a, base_ret))
                        for a in ids if a in account_returns)
        rates[bucket] = weighted / total
    return rates


def _gross_up(net_needed: float, source: str, ordinary_rate: float, ltcg_rate: float, gain_fraction: float) -> tuple[float, float]:
    """Return (gross_draw, tax_paid) for withdrawing enough from `source` to
    net `net_needed` dollars of spendable cash, under the simplified flat-rate
    model this module uses throughout."""
    if net_needed <= 0:
        return 0.0, 0.0
    if source == "roth":
        return net_needed, 0.0
    if source == "pretax":
        rate = max(0.0, min(0.55, ordinary_rate))
        gross = net_needed / max(1e-6, 1.0 - rate)
        return gross, gross * rate
    if source == "taxable":
        eff_rate = max(0.0, min(0.55, ltcg_rate)) * max(0.0, min(1.0, gain_fraction))
        gross = net_needed / max(1e-6, 1.0 - eff_rate)
        return gross, gross * eff_rate
    return net_needed, 0.0


def simulate_withdrawal_strategy(c: Mapping[str, Any], rows: list, strategy_key: str, ltcg_rate: float = 0.15) -> dict:
    """Approximate year-by-year simulation of one named strategy.

    `rows` is the REAL deterministic projection for this plan -- used only
    to read each year's already-computed RMD total and total elective
    withdrawal need (trust_wd + hsa_wd + roth_wd + ira_wd), not re-derived
    here. Balances are grown at a balance-weighted per-bucket rate derived
    from the same account_returns Wave 3.5 populates (bond-heavy pre-tax
    accounts and equity-heavy Roth accounts do not compound at the same
    rate -- using one flat blended rate for all three buckets understated
    growth enough to show this household depleting late in the plan when
    the real, per-account-differentiated engine shows it staying solvent)
    and depleted by RMDs (forced) plus this strategy's chosen sequence for
    the elective need, floored at zero (a depleted account simply can't
    fund more -- the shortfall rolls to the next account in the order,
    and to every remaining account in the 'proportional' strategy).
    """
    strategy = WITHDRAWAL_STRATEGIES[strategy_key]
    bal = _starting_balances_by_type(c)
    bucket_ret = _bucket_growth_rates(c)
    brk_inf = float(c.get("brk_inf", 0.02) or 0.02)
    filing = c.get("filing_status", "MFJ")
    gain_fraction = float(c.get("trust_gain_fraction", 0.50) or 0.50)
    plan_start = int(c.get("plan_start", rows[0].get("year", 0) if rows else 0) or 0)

    lifetime_tax = 0.0
    yearly = []
    for row in rows:
        year = int(row.get("year", plan_start))
        rmd = float(row.get("rmd_h", 0.0) or 0.0) + float(row.get("rmd_w", 0.0) or 0.0)
        elective_need = (
            float(row.get("trust_wd", 0.0) or 0.0)
            + float(row.get("hsa_wd", 0.0) or 0.0)
            + float(row.get("roth_wd", 0.0) or 0.0)
            + float(row.get("ira_wd", 0.0) or 0.0)
        )

        for k in ("pretax", "roth", "taxable"):
            bal[k] = max(0.0, bal[k] * (1.0 + bucket_ret[k]))

        # RMDs are forced from pre-tax regardless of strategy.
        rmd_draw = min(rmd, bal["pretax"])
        bal["pretax"] -= rmd_draw
        ordinary_rate = marginal_rate(max(0.0, elective_need + rmd_draw), year, filing, brk_inf)
        lifetime_tax += rmd_draw * max(0.0, min(0.55, ordinary_rate))

        remaining = elective_need
        if strategy_key == "current_plan":
            # This strategy IS the real plan, not a counterfactual reorder --
            # use the real per-account withdrawal split directly (ira_wd,
            # trust_wd, roth_wd) rather than re-deriving an allocation from
            # the summed elective_need through this module's own order-based
            # logic. The real plan already decides per-year how much comes
            # from each account (e.g. it may prefer trust/Roth over pretax
            # well beyond RMDs), and re-deriving that from a strategy order
            # would silently substitute this module's guess for the real
            # engine's actual, more tax-aware allocation -- defeating the
            # point of using "current plan" as the accurate baseline the
            # other strategies are compared against.
            for source, key in (("pretax", "ira_wd"), ("taxable", "trust_wd"), ("roth", "roth_wd")):
                want = float(row.get(key, 0.0) or 0.0)
                gross, tax = _gross_up(want, source, ordinary_rate, ltcg_rate, gain_fraction)
                draw = min(gross, bal[source])
                net_funded = draw * (1.0 - (tax / gross if gross > 0 else 0.0))
                bal[source] -= draw
                lifetime_tax += tax * (draw / gross if gross > 0 else 0.0)
                remaining -= net_funded
            remaining -= float(row.get("hsa_wd", 0.0) or 0.0)  # HSA not tracked in bal; matches reality (0 tax)
            # This module's simulated balances necessarily drift from the
            # real engine's over a multi-decade plan (simplified flat-rate
            # tax model vs the real bracket-aware one, no lot-level basis
            # tracking, ...), so by late in the horizon the real dollar
            # amount for one bucket can exceed what THIS simulation still
            # has in that bucket even though another bucket has room. Fall
            # through to the same account-priority order every other
            # strategy uses for any residual, rather than reporting a
            # shortfall while an untouched bucket sits available -- an
            # artifact of simulator drift, not a real funding gap.
            if remaining > 1e-6:
                for source in ("pretax", "taxable", "roth"):
                    if remaining <= 1e-6:
                        break
                    gross, tax = _gross_up(remaining, source, ordinary_rate, ltcg_rate, gain_fraction)
                    draw = min(gross, bal[source])
                    net_funded = draw * (1.0 - (tax / gross if gross > 0 else 0.0))
                    bal[source] -= draw
                    lifetime_tax += tax * (draw / gross if gross > 0 else 0.0)
                    remaining -= net_funded
        elif strategy["order"] == "proportional":
            total_bal = bal["pretax"] + bal["roth"] + bal["taxable"]
            shares = {k: (bal[k] / total_bal if total_bal > 0 else 0.0) for k in ("pretax", "roth", "taxable")}
            order = sorted(shares, key=lambda k: -shares[k])
            targets = {k: remaining * shares[k] for k in order}
            for k in order:
                want = targets[k]
                gross, tax = _gross_up(want, k, ordinary_rate, ltcg_rate, gain_fraction)
                draw = min(gross, bal[k])
                net_funded = draw * (1.0 - (tax / gross if gross > 0 else 0.0))
                bal[k] -= draw
                lifetime_tax += tax * (draw / gross if gross > 0 else 0.0)
                remaining -= net_funded
            # A per-bucket proportional TARGET can exceed that bucket's own
            # balance even while other buckets still have room (shares are
            # computed once per year, not re-normalized as buckets deplete
            # mid-year) -- fall back to whatever's left, same as the
            # current_plan branch above, rather than reporting a shortfall
            # while another bucket sits available.
            if remaining > 1e-6:
                for k in order:
                    if remaining <= 1e-6:
                        break
                    gross, tax = _gross_up(remaining, k, ordinary_rate, ltcg_rate, gain_fraction)
                    draw = min(gross, bal[k])
                    net_funded = draw * (1.0 - (tax / gross if gross > 0 else 0.0))
                    bal[k] -= draw
                    lifetime_tax += tax * (draw / gross if gross > 0 else 0.0)
                    remaining -= net_funded
            # Any residual (all accounts exhausted) is a real unfunded
            # shortfall, same convention as the real engine's UNFUNDED_GAP.
        else:
            for source in strategy["order"]:
                if remaining <= 1e-6 or source not in bal:
                    continue
                gross, tax = _gross_up(remaining, source, ordinary_rate, ltcg_rate, gain_fraction)
                draw = min(gross, bal[source])
                net_funded = draw * (1.0 - (tax / gross if gross > 0 else 0.0))
                bal[source] -= draw
                actual_tax = tax * (draw / gross if gross > 0 else 0.0)
                lifetime_tax += actual_tax
                remaining -= net_funded

        yearly.append({
            "year": year,
            "unfunded": max(0.0, remaining),
            "pretax": bal["pretax"], "roth": bal["roth"], "taxable": bal["taxable"],
        })

    terminal = yearly[-1] if yearly else {"pretax": 0.0, "roth": 0.0, "taxable": 0.0, "unfunded": 0.0}
    return {
        "strategy_key": strategy_key,
        "label": strategy["label"],
        "description": strategy["description"],
        "lifetime_tax_approx": lifetime_tax,
        "terminal_pretax": terminal["pretax"],
        "terminal_roth": terminal["roth"],
        "terminal_taxable": terminal["taxable"],
        "terminal_total_nw_approx": terminal["pretax"] + terminal["roth"] + terminal["taxable"],
        "years_with_shortfall": sum(1 for y in yearly if y["unfunded"] > 1.0),
        "yearly": yearly,
    }


def compare_withdrawal_strategies(c: Mapping[str, Any], rows: list, strategy_keys=None) -> list[dict]:
    """Run every (or a chosen subset of) named strategy and return their
    approximate outcomes, sorted by approximate lifetime tax ascending
    (lowest-tax strategy first) -- the planner's natural sort order for
    a sequencing comparison."""
    keys = list(strategy_keys) if strategy_keys else list(WITHDRAWAL_STRATEGIES.keys())
    results = [simulate_withdrawal_strategy(c, rows, k) for k in keys]
    results.sort(key=lambda r: r["lifetime_tax_approx"])
    return results
