import type { RunResult } from "../api";

/**
 * Derive a representative annual series for an asset from its stored results
 * snapshot. Used for the per-asset sparkline (a cheap trend cue on the card)
 * and, summed across the portfolio, the consolidated NAV/cash-flow curve.
 *
 * Preference order (most decision-relevant first):
 *  1. Generic models — net income per year (income statement). The bottom line.
 *  2. Generic models — operating cash flow (CFO) when there is no P&L.
 *  3. Legacy hybrid_consolidated — combined FV + BESS cash flows per year.
 *
 * Returns `[]` for a snapshot we cannot read (the card then hides its curve and
 * the asset simply does not contribute to the aggregated portfolio curve).
 */
export function assetAnnualSeries(snapshot: RunResult | null | undefined): number[] {
  if (!snapshot) return [];

  // 1 — net income (generic income statement).
  const ni = snapshot.income_statement?.rows?.net_income;
  if (Array.isArray(ni) && ni.length > 1) return ni.map(toNum);

  // 2 — operating cash flow (generic cash flow), when no P&L net line.
  const cfo = snapshot.cash_flow?.cfo;
  if (Array.isArray(cfo) && cfo.length > 1) return cfo.map(toNum);

  // 3 — legacy hybrid_consolidated combined cash flows.
  const hy = snapshot.cashflows;
  if (hy && Array.isArray(hy.years) && hy.years.length > 1) {
    return hy.years.map((_, i) => toNum(hy.fv?.[i]) + toNum(hy.bess?.[i]));
  }

  return [];
}

/**
 * Sum a set of per-asset annual series into a single consolidated series,
 * padding shorter horizons with zero so a 25y asset and a 30y asset align on
 * the same x-axis. Returns `[]` when there is nothing to consolidate.
 */
export function consolidateSeries(seriesList: number[][]): number[] {
  const usable = seriesList.filter((s) => s.length > 0);
  if (usable.length === 0) return [];
  const horizon = Math.max(...usable.map((s) => s.length));
  const out = new Array<number>(horizon).fill(0);
  for (const s of usable) {
    for (let i = 0; i < s.length; i += 1) out[i] += toNum(s[i]);
  }
  return out;
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
