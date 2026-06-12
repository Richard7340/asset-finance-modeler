import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getPortfolio, listAssets } from "../api";
import type { PortfolioAsset, SavedAssetSummary } from "../api";
import { eur, eurExact, pct } from "../format";
import AnimatedNumber from "./AnimatedNumber";
import Reveal, { useStaggerReveal } from "./Reveal";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

const NPV_BAR = "#4f46e5"; // indigo-600
const NPV_BAR_NEG = "#f43f5e";
const REV_BAR = "#64748b";

// Restrained categorical ramp (indigo → slate) for the composition donut.
const DONUT = [
  "#4f46e5",
  "#6366f1",
  "#818cf8",
  "#a5b4fc",
  "#6b7280",
  "#94a3b8",
  "#0ea5e9",
  "#38bdf8",
];

// Sober, restrained tones for error-spotting cues (no loud colors, no emojis).
const NEG = "text-rose-700";
const WARN = "text-amber-600";
const MUTE = "text-slate-400";

function moneyTone(v: number | undefined): string {
  if (v === undefined || !Number.isFinite(v)) return MUTE;
  if (v === 0) return WARN;
  if (v < 0) return NEG;
  return "text-slate-800";
}

function rateTone(v: number | undefined): string {
  if (v === undefined || !Number.isFinite(v)) return MUTE;
  if (v < 0) return NEG;
  return "text-slate-800";
}

const tooltipStyle = {
  fontSize: 12,
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  boxShadow: "0 6px 24px rgb(15 23 42 / 0.10)",
  padding: "8px 10px",
};

function Kpi({
  label,
  value,
  format,
  text,
  hint,
}: {
  label: string;
  value?: number;
  format?: (n: number) => string;
  /** Plain text value (e.g. asset count) when not a count-up figure. */
  text?: string;
  hint?: string;
}) {
  return (
    <div className="surface surface-hover relative overflow-hidden p-4">
      <span
        className="absolute inset-y-3 left-0 w-0.5 rounded-full bg-accent-500/60"
        aria-hidden
      />
      <div className="pl-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </div>
        {text !== undefined ? (
          <div className="mt-1.5 text-2xl font-semibold tabular-nums text-slate-900">
            {text}
          </div>
        ) : (
          <AnimatedNumber
            value={value ?? 0}
            format={format ?? ((n) => String(n))}
            className="mt-1.5 block text-2xl font-semibold tabular-nums text-slate-900"
          />
        )}
        {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
      </div>
    </div>
  );
}

export default function PortfolioOverview({ onOpenAsset }: Props) {
  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: listAssets });
  const allAssets = assetsQuery.data ?? [];

  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  const includedIds = useMemo(
    () => allAssets.map((a) => a.id).filter((id) => !excluded.has(id)),
    [allAssets, excluded],
  );

  const allIncluded = excluded.size === 0;
  const portfolioQuery = useQuery({
    queryKey: ["portfolio", allIncluded ? "all" : includedIds.join(",")],
    queryFn: () => getPortfolio(allIncluded ? undefined : includedIds),
  });

  const portfolio = portfolioQuery.data;
  const totals = portfolio?.totals;

  const metricsById = useMemo(() => {
    const m = new Map<string, PortfolioAsset>();
    for (const a of portfolio?.assets ?? []) m.set(a.id, a);
    return m;
  }, [portfolio]);

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

  const chartData = useMemo(
    () =>
      (portfolio?.assets ?? [])
        .map((a) => ({ name: a.name, npv: a.npv }))
        .sort((x, y) => y.npv - x.npv),
    [portfolio],
  );

  const revChartData = useMemo(
    () =>
      (portfolio?.assets ?? [])
        .map((a) => ({ name: a.name, revenue_y1: a.revenue_y1 }))
        .sort((x, y) => y.revenue_y1 - x.revenue_y1),
    [portfolio],
  );

  // Composition donut: share of total VAN, positive contributors only, sorted.
  const compositionData = useMemo(() => {
    const positives = (portfolio?.assets ?? [])
      .filter((a) => a.npv > 0)
      .map((a) => ({ name: a.name, value: a.npv }))
      .sort((x, y) => y.value - x.value);
    return positives;
  }, [portfolio]);
  const compositionTotal = useMemo(
    () => compositionData.reduce((s, d) => s + d.value, 0),
    [compositionData],
  );

  // Re-stagger KPIs and rows whenever the composition of the portfolio changes.
  const kpiRef = useStaggerReveal<HTMLDivElement>([rows.length, allIncluded]);
  const rowsRef = useStaggerReveal<HTMLTableSectionElement>(
    [rows.length],
    { selector: "tr", gap: 28, y: 6 },
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
      <span className="h-2 w-2 animate-pulse rounded-full bg-accent-500" />
      recalculando…
    </span>
  ) : null;

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            Vista de cartera
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Centro de control de activos · valoración consolidada
          </p>
        </div>
        {recalcBadge}
      </div>

      {/* Aggregate KPIs */}
      <div
        ref={kpiRef}
        className={`grid grid-cols-2 gap-3 ${
          totals?.irr_weighted !== undefined ? "sm:grid-cols-5" : "sm:grid-cols-4"
        }`}
      >
        <Kpi label="VAN total" value={totals?.npv ?? 0} format={eur} />
        <Kpi label="CAPEX total" value={totals?.capex ?? 0} format={eur} />
        <Kpi label="Ingresos año 1" value={totals?.revenue_y1 ?? 0} format={eur} />
        {totals?.irr_weighted !== undefined && (
          <Kpi
            label="TIR media"
            value={totals.irr_weighted}
            format={pct}
            hint="ponderada por CAPEX"
          />
        )}
        <Kpi
          label="Nº activos"
          text={String(totals?.count ?? 0)}
          hint={
            excluded.size > 0
              ? `${excluded.size} excluido${excluded.size === 1 ? "" : "s"}`
              : undefined
          }
        />
      </div>

      {/* Composition donut + VAN bars side by side */}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Reveal className="surface surface-hover p-4">
          <h3 className="mb-1 text-sm font-semibold text-slate-800">
            Composición de cartera
          </h3>
          <p className="mb-2 text-[11px] text-slate-400">
            Peso de cada activo sobre el VAN positivo total
          </p>
          {compositionData.length > 0 ? (
            <div className="relative h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={compositionData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius="58%"
                    outerRadius="86%"
                    paddingAngle={1.5}
                    stroke="#fff"
                    strokeWidth={2}
                    animationDuration={800}
                  >
                    {compositionData.map((d, i) => (
                      <Cell key={d.name} fill={DONUT[i % DONUT.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number, n: string) => [
                      `${eur(Number(v))} · ${pct(
                        compositionTotal ? Number(v) / compositionTotal : 0,
                      )}`,
                      n,
                    ]}
                    contentStyle={tooltipStyle}
                  />
                </PieChart>
              </ResponsiveContainer>
              {/* Center label */}
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">
                  VAN total
                </div>
                <div className="text-lg font-semibold tabular-nums text-slate-900">
                  {eur(totalNpv)}
                </div>
              </div>
            </div>
          ) : (
            <div className="grid h-72 place-items-center text-xs text-slate-400">
              Sin activos con VAN positivo.
            </div>
          )}
        </Reveal>

        <Reveal className="surface surface-hover p-4" delay={60}>
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            VAN por activo
          </h3>
          <div className="h-72 w-full">
            {chartData.length > 0 ? (
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
                    contentStyle={tooltipStyle}
                    cursor={{ fill: "rgb(99 102 241 / 0.06)" }}
                  />
                  <Bar dataKey="npv" name="VAN" radius={[0, 4, 4, 0]} animationDuration={800}>
                    {chartData.map((d) => (
                      <Cell key={d.name} fill={d.npv >= 0 ? NPV_BAR : NPV_BAR_NEG} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : null}
          </div>
        </Reveal>
      </div>

      {/* Per-asset table */}
      <Reveal className="surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-medium uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2.5 font-medium">Incl.</th>
              <th className="px-3 py-2.5 font-medium">Activo</th>
              <th className="px-3 py-2.5 font-medium">Tipo / Modelo</th>
              <th className="px-3 py-2.5 text-right font-medium">VAN</th>
              <th className="px-3 py-2.5 text-right font-medium">TIR</th>
              <th className="px-3 py-2.5 text-right font-medium">Rentabilidad</th>
              <th className="px-3 py-2.5 text-right font-medium">Ingresos año 1</th>
              <th className="px-3 py-2.5 text-right font-medium">CAPEX</th>
              <th className="px-3 py-2.5 text-right font-medium">% VAN</th>
            </tr>
          </thead>
          <tbody ref={rowsRef}>
            {rows.map((r) => {
              const m = metricsById.get(r.id);
              const isIncluded = !excluded.has(r.id);
              const contrib = m && totalNpv !== 0 ? m.npv / totalNpv : 0;
              return (
                <tr
                  key={r.id}
                  className={`border-b border-slate-100 transition last:border-0 hover:bg-accent-50/40 ${
                    isIncluded ? "" : "bg-slate-50/60 text-slate-400"
                  }`}
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={isIncluded}
                      onChange={() => toggle(r.id)}
                      aria-label={`Incluir ${r.name} en el agregado`}
                      className="h-4 w-4 cursor-pointer accent-accent-600"
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => openById(r.id)}
                      className="text-left font-medium text-slate-800 transition hover:text-accent-700 hover:underline"
                    >
                      {r.name}
                    </button>
                  </td>
                  <td className="px-3 py-2.5 text-slate-500">{r.model_id}</td>
                  <td
                    className={`px-3 py-2.5 text-right tabular-nums ${
                      isIncluded ? rateTone(m?.npv) : ""
                    }`}
                  >
                    {m ? eurExact(m.npv) : "—"}
                  </td>
                  <td
                    className={`px-3 py-2.5 text-right tabular-nums ${
                      isIncluded ? rateTone(m?.irr) : ""
                    }`}
                  >
                    {m && Number.isFinite(m.irr) ? pct(m.irr) : "—"}
                  </td>
                  <td
                    className={`px-3 py-2.5 text-right tabular-nums ${
                      isIncluded ? rateTone(m?.yield_pct) : ""
                    }`}
                  >
                    {m && Number.isFinite(m.yield_pct) ? pct(m.yield_pct) : "—"}
                  </td>
                  <td
                    className={`px-3 py-2.5 text-right tabular-nums ${
                      isIncluded ? moneyTone(m?.revenue_y1) : ""
                    }`}
                  >
                    {m ? eurExact(m.revenue_y1) : "—"}
                  </td>
                  <td
                    className={`px-3 py-2.5 text-right tabular-nums ${
                      isIncluded ? moneyTone(m?.capex) : ""
                    }`}
                  >
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
      </Reveal>

      {/* Año-1 revenue per asset */}
      {revChartData.length > 0 && (
        <Reveal className="surface surface-hover p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">
            Ingresos año 1 por activo
          </h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={revChartData}
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
                  contentStyle={tooltipStyle}
                  cursor={{ fill: "rgb(99 102 241 / 0.06)" }}
                />
                <Bar dataKey="revenue_y1" name="Ingresos año 1" fill={REV_BAR} radius={[0, 4, 4, 0]} animationDuration={800} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Reveal>
      )}
    </div>
  );
}
