import { useQueries } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { getLive, getVariance, listAssets } from "../api";
import type { LiveResult, SavedAssetSummary, Variance } from "../api";

// Operational thresholds (sober, fund-grade): a variance beyond ±10% on any
// tracked line, or a live minimum DSCR below 1.0 (debt cannot be serviced).
const DEV_THRESHOLD = 0.1;
const DSCR_FLOOR = 1.0;

type Severity = "warn" | "info";

type Alert = {
  assetId: string;
  assetName: string;
  severity: Severity;
  message: string;
};

/** Worst |deviation_pct| across tracked lines, with the offending line. */
function varianceAlerts(name: string, id: string, v: Variance): Alert[] {
  const out: Alert[] = [];
  for (const line of v.lines) {
    let worst: number | null = null;
    let worstYear = -1;
    line.deviation_pct.forEach((d, i) => {
      if (d != null && Number.isFinite(d) && (worst == null || Math.abs(d) > Math.abs(worst))) {
        worst = d;
        worstYear = i + 1;
      }
    });
    if (worst != null && Math.abs(worst) > DEV_THRESHOLD) {
      const sign = worst > 0 ? "+" : "";
      out.push({
        assetId: id,
        assetName: name,
        severity: "warn",
        message: `${line.label}: desviación ${sign}${(worst * 100).toLocaleString(
          "es-ES",
          { maximumFractionDigits: 1 },
        )}% sobre base (año ${worstYear})`,
      });
    }
  }
  return out;
}

/** Live minimum DSCR below the floor. */
function liveAlerts(name: string, id: string, l: LiveResult): Alert[] {
  const dscr = l.comparison.dscr_min_live;
  if (Number.isFinite(dscr) && dscr > 0 && dscr < DSCR_FLOOR) {
    return [
      {
        assetId: id,
        assetName: name,
        severity: "warn",
        message: `DSCR mínimo live ${dscr.toLocaleString("es-ES", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}× por debajo de 1,00×`,
      },
    ];
  }
  return [];
}

function AlertRow({ a, showAsset }: { a: Alert; showAsset: boolean }) {
  return (
    <li className="flex items-start gap-2.5 px-3 py-2 text-sm">
      <AlertTriangle
        size={15}
        strokeWidth={2}
        className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-500"
        aria-hidden
      />
      <div className="min-w-0">
        {showAsset && (
          <span className="font-medium text-slate-700">{a.assetName} · </span>
        )}
        <span className="text-slate-600">{a.message}</span>
      </div>
    </li>
  );
}

function AlertList({
  alerts,
  showAsset,
  title,
}: {
  alerts: Alert[];
  showAsset: boolean;
  title: string;
}) {
  if (alerts.length === 0) {
    return (
      <section className="surface p-3">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <CheckCircle2 size={15} strokeWidth={2} className="text-emerald-600" aria-hidden />
          {title}: sin alertas. Las desviaciones están dentro de umbral.
        </div>
      </section>
    );
  }
  return (
    <section className="surface overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-3 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <AlertTriangle size={15} strokeWidth={2} className="text-amber-600" aria-hidden />
          {title}
        </h3>
        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium tabular-nums text-amber-700 dark:text-amber-400">
          {alerts.length}
        </span>
      </div>
      <ul className="divide-y divide-slate-100">
        {alerts.map((a, i) => (
          <AlertRow key={`${a.assetId}-${i}`} a={a} showAsset={showAsset} />
        ))}
      </ul>
    </section>
  );
}

/**
 * Single-asset alerts for the detail view: variance beyond ±10% or live DSCR
 * below 1.0. Sober amber cue, lucide AlertTriangle, no loud reds.
 */
export function AssetAlerts({ assetId }: { assetId: string }) {
  const results = useQueries({
    queries: [
      { queryKey: ["variance", assetId], queryFn: () => getVariance(assetId) },
      { queryKey: ["live", assetId], queryFn: () => getLive(assetId) },
    ],
  });
  const [variance, live] = results;

  if (results.some((r) => r.isLoading)) {
    return <div className="p-2 text-sm text-slate-400">Comprobando alertas…</div>;
  }

  const alerts: Alert[] = [];
  if (variance.data) alerts.push(...varianceAlerts("", assetId, variance.data));
  if (live.data) alerts.push(...liveAlerts("", assetId, live.data));

  return <AlertList alerts={alerts} showAsset={false} title="Alertas operativas" />;
}

/**
 * Portfolio alerts for the dashboard: scans every operational asset's variance
 * and live reprojection and surfaces those breaching the thresholds.
 */
export function PortfolioAlerts() {
  const assetsQuery = useQueries({
    queries: [{ queryKey: ["assets", "operational"], queryFn: () => listAssets("operational") }],
  });
  const assets: SavedAssetSummary[] = assetsQuery[0].data ?? [];

  const varianceQueries = useQueries({
    queries: assets.map((a) => ({
      queryKey: ["variance", a.id],
      queryFn: () => getVariance(a.id),
    })),
  });
  const liveQueries = useQueries({
    queries: assets.map((a) => ({
      queryKey: ["live", a.id],
      queryFn: () => getLive(a.id),
    })),
  });

  const loading =
    assetsQuery[0].isLoading ||
    varianceQueries.some((q) => q.isLoading) ||
    liveQueries.some((q) => q.isLoading);

  if (loading) {
    return <div className="p-2 text-sm text-slate-400">Comprobando alertas…</div>;
  }

  const alerts: Alert[] = [];
  assets.forEach((a, i) => {
    const v = varianceQueries[i]?.data;
    const l = liveQueries[i]?.data;
    if (v) alerts.push(...varianceAlerts(a.name, a.id, v));
    if (l) alerts.push(...liveAlerts(a.name, a.id, l));
  });

  // Don't render the "all clear" card when there are no operational assets at
  // all — there is simply nothing to monitor yet.
  if (assets.length === 0) return null;

  return <AlertList alerts={alerts} showAsset title="Alertas de cartera" />;
}
