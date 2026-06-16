import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { getAsset } from "../api";
import { assetAnnualSeries } from "../lib/assetSeries";

/**
 * Fetch a representative annual series for each given asset id and expose them
 * both per-asset (for card sparklines) and consolidated (for the portfolio
 * curve). Designed to stay cheap:
 *  - one query per asset, run in parallel;
 *  - cached forever (snapshots are frozen results), so revisiting / toggling
 *    the include set never refetches;
 *  - the cards render instantly from portfolio totals regardless — the series
 *    only enrich them as they arrive.
 */
export function useAssetSeries(ids: string[]): {
  /** Map of asset id → annual series (empty array if unreadable / not yet loaded). */
  byId: Map<string, number[]>;
  /** Whether any series query is still in flight. */
  loading: boolean;
} {
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["asset-series", id],
      queryFn: () => getAsset(id),
      staleTime: Infinity,
      gcTime: 30 * 60_000,
    })),
  });

  const byId = useMemo(() => {
    const m = new Map<string, number[]>();
    ids.forEach((id, i) => {
      const data = results[i]?.data;
      m.set(id, data ? assetAnnualSeries(data.results_snapshot) : []);
    });
    return m;
    // results identity changes each render; key on the stable inputs instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(","), results.map((r) => (r.data ? 1 : 0)).join("")]);

  const loading = results.some((r) => r.isLoading);

  return { byId, loading };
}
