import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getPortfolio, listAssets } from "../api";
import type { PortfolioAsset, SavedAssetSummary } from "../api";
import { eur, eurExact, pct } from "../format";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

const NPV_BAR = "#0ea5e9";
const NPV_BAR_NEG = "#f43f5e";

function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-800">
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export default function PortfolioOverview({ onOpenAsset }: Props) {
  // The full saved-asset list (for the row drill-in handler and the
  // "are there any assets at all?" empty-state decision).
  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: listAssets });
  const allAssets = assetsQuery.data ?? [];

  // Which assets are included in the aggregate. `null` = "all" (default).
  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  const includedIds = useMemo(
    () => allAssets.map((a) => a.id).filter((id) => !excluded.has(id)),
    [allAssets, excluded],
  );

  // Portfolio aggregate, scoped to the included ids. When all are included we
  // pass no ids so the backend counts everything (and a newly saved asset that
  // isn't in `allAssets` yet still shows up after invalidation).
  const allIncluded = excluded.size === 0;
  const portfolioQuery = useQuery({
    queryKey: ["portfolio", allIncluded ? "all" : includedIds.join(",")],
    queryFn: () => getPortfolio(allIncluded ? undefined : includedIds),
  });

  const portfolio = portfolioQuery.data;
  const totals = portfolio?.totals;

  // Show every saved asset in the table (even excluded ones) so the user can
  // re-include them. The aggregate query only returns included assets, so we
  // merge: rows come from the portfolio (with metrics) plus any excluded asset
  // re-fetched separately would be wasteful — instead we keep a metrics map.
  const metricsById = useMemo(() => {
    const m = new Map<string, PortfolioAsset>();
    for (const a of portfolio?.assets ?? []) m.set(a.id, a);
    return m;
  }, [portfolio]);

  // Asset list to render rows for: the union of saved assets and any returned
  // by the portfolio query (covers freshly-saved-before-list-refresh).
  const rows = useMemo(() => {
    const byId = new Map<string, { id: string; name: string; model_id: string }>();
    for (const a of allAssets)
      byId.set(a.id, { id: a.id, name: a.name, model_id: a.model_id });
    for (const a of portfolio?.assets ?? [])
      if (!byId.has(a.id))
        byId.set(a.id, { id: a.id, name: a.name, model_id: a.model_id });
    return [...byId.values()];
  }, [allAssets, portfolio]);

  const toggle = (id: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const openById = (id: string) => {
    const a = allAssets.find((x) => x.id === id);
    if (a) onOpenAsset(a);
  };

  const totalNpv = totals?.npv ?? 0;

  // Bar chart data: VAN per included asset, sorted descending.
  const chartData = useMemo(
    () =>
      (portfolio?.assets ?? [])
        .map((a) => ({ name: a.name, npv: a.npv }))
        .sort((x, y) => y.npv - x.npv),
    [portfolio],
  );

  // --- empty / loading states ---
  if (assetsQuery.isLoading || portfolioQuery.isLoading) {
    return (
      <div className="grid h-64 place-items-center text-sm text-slate-400">
        Cargando cartera…
      </div>
    );
  }

  if (allAssets.length === 0 && (portfolio?.assets.length ?? 0) === 0) {
    return (
      <div className="grid h-64 place-items-center px-6 text-center text-sm text-slate-400">
        Aún no hay activos guardados. Crea y guarda un activo desde un modelo.
      </div>
    );
  }

  const recalcBadge = portfolioQuery.isFetching ? (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
      recalculando…
    </span>
  ) : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Vista de cartera
        </h2>
        {recalcBadge}
      </div>

      {/* Aggregate KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="VAN total" value={eur(totals?.npv ?? 0)} />
        <Kpi label="CAPEX total" value={eur(totals?.capex ?? 0)} />
        <Kpi label="Ingresos año 1" value={eur(totals?.revenue_y1 ?? 0)} />
        <Kpi
          label="Nº activos"
          value={String(totals?.count ?? 0)}
          hint={
            excluded.size > 0
              ? `${excluded.size} excluido${excluded.size === 1 ? "" : "s"}`
              : undefined
          }
        />
      </div>

      {/* Per-asset table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-[11px] font-medium uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2.5 font-medium">Incl.</th>
              <th className="px-3 py-2.5 font-medium">Activo</th>
              <th className="px-3 py-2.5 font-medium">Tipo / Modelo</th>
              <th className="px-3 py-2.5 text-right font-medium">VAN</th>
              <th className="px-3 py-2.5 text-right font-medium">Ingresos año 1</th>
              <th className="px-3 py-2.5 text-right font-medium">CAPEX</th>
              <th className="px-3 py-2.5 text-right font-medium">% VAN</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const m = metricsById.get(r.id);
              const isIncluded = !excluded.has(r.id);
              const contrib =
                m && totalNpv !== 0 ? m.npv / totalNpv : 0;
              return (
                <tr
                  key={r.id}
                  className={`border-b border-slate-100 last:border-0 transition ${
                    isIncluded ? "" : "bg-slate-50/60 text-slate-400"
                  }`}
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={isIncluded}
                      onChange={() => toggle(r.id)}
                      aria-label={`Incluir ${r.name} en el agregado`}
                      className="h-4 w-4 cursor-pointer accent-sky-600"
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => openById(r.id)}
                      className="text-left font-medium text-slate-800 hover:text-sky-700 hover:underline"
                    >
                      {r.name}
                    </button>
                  </td>
                  <td className="px-3 py-2.5 text-slate-500">{r.model_id}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {m ? eurExact(m.npv) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {m ? eurExact(m.revenue_y1) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {m ? eurExact(m.capex) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-600">
                    {m && isIncluded ? pct(contrib) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* VAN per asset bar chart */}
      {chartData.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            VAN por activo
          </h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ left: 8, right: 16 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v: number) => eur(Number(v))}
                  fontSize={11}
                  stroke="#94a3b8"
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  fontSize={11}
                  stroke="#94a3b8"
                  width={140}
                />
                <Tooltip
                  formatter={(v: number) => eur(Number(v))}
                  contentStyle={{ fontSize: 12 }}
                />
                <Bar dataKey="npv" name="VAN">
                  {chartData.map((d) => (
                    <Cell key={d.name} fill={d.npv >= 0 ? NPV_BAR : NPV_BAR_NEG} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
