// The one place that decides how a money amount is written: dollars, or a percent of today's net worth.
// A "percent" person's /api/ data is already divided by today's net worth on the server (scale 1);
// the owner's own page divides by today's net worth read from /api/balances.

let state = { allowed: "both", shown: "dollars", scale: 1 };
const listeners = [];

export function setMoneyView({ allowed = "both", shown, scale = 1 } = {}) {
  const forced = allowed === "percent" ? "percent" : allowed === "dollars" ? "dollars" : null;
  state = { allowed, shown: forced || (shown === "percent" ? "percent" : "dollars"), scale };
  for (const fn of listeners) fn(moneyView());
}

export function moneyView() {
  return { ...state };
}

export function onMoneyViewChange(fn) {
  listeners.push(fn);
}

export function fmtAmount(v, digits = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "-";
  if (state.shown === "dollars") {
    return "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
  }
  if (!(state.scale > 0)) return "n/a";
  return `${(Number(v) / state.scale * 100).toFixed(1)}% of net worth`;
}

export function fmtSharePct(ratio) {
  if (ratio === null || ratio === undefined || !Number.isFinite(Number(ratio))) return "n/a";
  const pct = Number(ratio) * 100;
  return `${pct < 0 ? "-" : "+"}${Math.abs(pct).toFixed(1)}%`;
}

// Today's net worth: the last finite value of the balances payload's points.networth ({date, value}).
// 0 when there is none, so the percent view says "n/a" instead of dividing by a made-up number.
export function netWorthScale(balances) {
  const pts = balances && balances.points && balances.points.networth;
  if (Array.isArray(pts)) {
    for (let i = pts.length - 1; i >= 0; i--) {
      const v = pts[i] && pts[i].value;
      if (v !== null && v !== undefined && Number.isFinite(Number(v))) return Number(v);
    }
  }
  return 0;
}
