import { useMemo, useState } from "react";
import type React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, LayoutGrid } from "lucide-react";
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
import Sparkline from "./Sparkline";
import Reveal, { useStaggerReveal } from "./Reveal";
import { useChartTheme } from "../hooks/useChartTheme";
import { useAssetSeries } from "../hooks/useAssetSeries";
import { consolidateSeries } from "../lib/assetSeries";
import AssetCards from "./AssetCards";
import PortfolioCurve from "./PortfolioCurve";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
  /** Restrict the listing+aggregate to one lifecycle bucket. */
  lifecycle?: import("../api").Lifecycle;
  /** Optional action column rendered per row (e.g. "Marcar en operación"). */
  rowAction?: (a: SavedAssetSummary) => React.ReactNode;
  /**
   * Premium page header. Receives the live aggregate so the headline numbers
   * (NAV / nº activos) sit at the very top of the page.
   */
  header?: (agg: HeaderAggregate) => React.ReactNode;
  /**
   * Slot rendered between the KPI band and the analytics panels (e.g. the
   * operational alerts strip on Cartera). Kept slim by the caller.
   */
  alertsSlot?: React.ReactNode;
  /**
   * Slot rendered at the very bottom of the page, after the table (e.g. the
   * operational assets map on Cartera).
   */
  mapSlot?: React.ReactNode;
};

/** Live aggregate surfaced to the page header render-prop. */
export type HeaderAggregate = {
  /** Total VAN / NAV across included assets. */
  navTotal: number;
  /** Number of included assets. */
  count: number;
  /** CAPEX-weighted IRR, decimal, when available. */
  irrWeighted?: number;
  /** Whether the aggregate is still loading. */
  loading: boolean;
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

function Kpi({
  label,
  value,
  format,
  text,
  hint,
  series,
  emphasis,
}: {
  label: string;
  value?: number;
  format?: (n: number) => string;
  /** Plain text value (e.g. asset count) when not a count-up figure. */
  text?: string;
  hint?: string;
  /** Optional mini-trend (e.g. per-asset distribution) rendered to the right. */
  series?: number[];
  /** Headline tile — larger figure + stronger accent rule. */
  emphasis?: boolean;
}) {
  const hasSpark = Array.isArray(series) && series.filter(Number.isFinite).length >= 2;
  return (
    <div className="surface surface-hover relative overflow-hidden p-4">
      <span
        className={`absolute inset-y-3 left-0 rounded-full ${
          emphasis ? "w-[3px] bg-accent-500" : "w-0.5 bg-accent-500/60"
        }`}
        aria-hidden
      />
      <div className="pl-2.5">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </div>
        <div className="mt-1.5 flex items-end justify-between gap-2">
          {text !== undefined ? (
            <div
              className={`font-semibold tabular-nums text-slate-900 ${
                emphasis ? "text-3xl" : "text-2xl"
              }`}
            >
              {text}
            </div>
          ) : (
            <AnimatedNumber
              value={value ?? 0}
              format={format ?? ((n) => String(n))}
              className={`block font-semibold tabular-nums text-slate-900 ${
                emphasis ? "text-3xl" : "text-2xl"
              }`}
            />
          )}
          {hasSpark && (
            <Sparkline values={series as number[]} className="shrink-0 opacity-90" />
          )}
        </div>
        {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
      </div>
    </div>
  );
}

/** Small section label used above each analytics panel / band. */
function PanelTitle({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[11px] text-slate-400">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export default function PortfolioOverview({
  onOpenAsset,
  lifecycle,
  rowAction,
  header,
  alertsSlot,
  mapSlot,
}: Props) {
  const ct = useChartTheme();
  const tooltipStyle = ct.tooltip;
  const cursorFill = ct.dark ? "rgb(99 102 241 / 0.14)" : "rgb(99 102 241 / 0.06)";
  const assetsQuery = useQuery({
    queryKey: ["assets", lifecycle ?? "all"],
    queryFn: () => listAssets(lifecycle),
  });
  const allAssets = assetsQuery.data ?? [];

  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  const includedIds = useMemo(
    () => allAssets.map((a) => a.id).filter((id) => !excluded.has(id)),
    [allAssets, excluded],
  );

  const allIncluded = excluded.size === 0;
  const portfolioQuery = useQuery({
    queryKey: ["portfolio", lifecycle ?? "all", allIncluded ? "all" : includedIds.join(",")],
    queryFn: () =>
      getPortfolio({ lifecycle, ids: allIncluded ? undefined : includedIds }),
  });

  const portfolio = portfolioQuery.data;
  const totals = portfolio?.totals;

  const metricsById = useMemo(() => {
    const m = new Map<string, PortfolioAsset>();
    for (const a of portfolio?.assets ?? []) m.set(a.id, a);
    return m;
  }, [portfolio]);

  const rows = useMemo(() => {
    const byId = new Map<
      string,
      { id: string; name: string; model_id: string; location?: string | null }
    >();
    for (const a of allAssets)
      byId.set(a.id, {
        id: a.id,
        name: a.name,
        model_id: a.model_id,
        location: a.location,
      });
    for (const a of portfolio?.assets ?? [])
      if (!byId.has(a.id))
        byId.set(a.id, {
          id: a.id,
          name: a.name,
          model_id: a.model_id,
          location: a.location,
        });
    return [...byId.values()];
  }, [allAssets, portfolio]);

  // Per-asset annual series (cheap, cached) → card sparklines + the
  // consolidated portfolio curve. Only the included assets contribute.
  const seriesIds = useMemo(
    () => rows.map((r) => r.id).filter((id) => !excluded.has(id)),
    [rows, excluded],
  );
  const { byId: seriesById, loading: seriesLoading } = useAssetSeries(seriesIds);
  const portfolioCurve = useMemo(
    () => consolidateSeries(seriesIds.map((id) => seriesById.get(id) ?? [])),
    [seriesIds, seriesById],
  );

  // Detail table: kept available below the cards (collapsed by default so the
  // cards lead, but always reachable for the dense figures + row actions).
  const [tableOpen, setTableOpen] = useState(false);
  const resolveAsset = (id: string): SavedAssetSummary | undefined =>
    allAssets.find((x) => x.id === id);

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

  const headerNode =
    header?.({
      navTotal: totals?.npv ?? 0,
      count: totals?.count ?? rows.length,
      irrWeighted: totals?.irr_weighted,
      loading: assetsQuery.isLoading || portfolioQuery.isLoading,
    }) ?? null;

  // --- empty / loading states ---
  if (assetsQuery.isLoading || portfolioQuery.isLoading) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-6">
        {headerNode}
        <div className="grid h-64 place-items-center text-sm text-slate-400">
          Cargando cartera…
        </div>
      </div>
    );
  }

  if (allAssets.length === 0 && (portfolio?.assets.length ?? 0) === 0) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-6">
        {headerNode}
        <div className="grid h-64 place-items-center px-6 text-center text-sm text-slate-400">
          Aún no hay activos guardados. Crea y guarda un activo desde un modelo.
        </div>
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
      {/* 0 — premium page header (headline NAV / nº activos). */}
      {headerNode}

      {/* 1 — KPI band: the headline numbers, grouped as a strong top band. */}
      <Reveal>
        <div className="flex items-center justify-between gap-3 pb-1">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
            Indicadores agregados
          </h3>
          {recalcBadge}
        </div>
        <div
          ref={kpiRef}
          className={`grid grid-cols-2 gap-3 ${
            totals?.irr_weighted !== undefined ? "sm:grid-cols-5" : "sm:grid-cols-4"
          }`}
        >
          <Kpi
            label="VAN total"
            value={totals?.npv ?? 0}
            format={eur}
            series={chartData.map((d) => d.npv)}
            emphasis
          />
          <Kpi label="CAPEX total" value={totals?.capex ?? 0} format={eur} />
          <Kpi
            label="Ingresos año 1"
            value={totals?.revenue_y1 ?? 0}
            format={eur}
            series={revChartData.map((d) => d.revenue_y1)}
          />
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
      </Reveal>

      {/* 2 — alerts strip (Cartera only; kept slim by the caller). */}
      {alertsSlot}

      {/* 3 — ASSETS, at a glance (the hero): a grid of rich asset cards. The
          dense detail table (include toggle + row actions) stays available
          right below, collapsed by default. */}
      <Reveal className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
            <LayoutGrid size={13} strokeWidth={2} className="text-accent-500" />
            Activos
          </h3>
          <span className="text-[11px] text-slate-400">
            {rows.length} activo{rows.length === 1 ? "" : "s"}
            {excluded.size > 0 ? ` · ${excluded.size} excluido${excluded.size === 1 ? "" : "s"}` : ""}
          </span>
        </div>

        <AssetCards
          rows={rows}
          metricsById={metricsById}
          seriesById={seriesById}
          excluded={excluded}
          totalNpv={totalNpv}
          lifecycle={lifecycle}
          onToggle={toggle}
          onOpen={openById}
          rowAction={rowAction}
          resolveAsset={resolveAsset}
        />

        {/* Detail table toggle — dense figures + the same include/actions. */}
        <button
          type="button"
          onClick={() => setTableOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-md px-1 py-1 text-xs font-medium text-slate-500 transition hover:text-accent-700"
          aria-expanded={tableOpen}
        >
          {tableOpen ? (
            <ChevronDown size={14} strokeWidth={2} />
          ) : (
            <ChevronRight size={14} strokeWidth={2} />
          )}
          {tableOpen ? "Ocultar tabla detallada" : "Ver tabla detallada"}
        </button>

        {tableOpen && (
          <div className="surface overflow-hidden">
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
                  {rowAction && (
                    <th className="px-3 py-2.5 text-right font-medium">Acción</th>
                  )}
                </tr>
              </thead>
              <tbody ref={rowsRef}>
                {rows.map((r, ri) => {
                  const m = metricsById.get(r.id);
                  const isIncluded = !excluded.has(r.id);
                  const contrib = m && totalNpv !== 0 ? m.npv / totalNpv : 0;
                  return (
                    <tr
                      key={r.id}
                      className={`group cursor-pointer border-b border-slate-100 transition last:border-0 hover:bg-accent-50/40 ${
                        ri % 2 === 1 ? "bg-slate-50/40" : ""
                      } ${isIncluded ? "" : "bg-slate-50/60 text-slate-400"}`}
                      onClick={() => openById(r.id)}
                    >
                      <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isIncluded}
                          onChange={() => toggle(r.id)}
                          aria-label={`Incluir ${r.name} en el agregado`}
                          className="h-4 w-4 cursor-pointer accent-accent-600"
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="font-medium text-slate-800 transition group-hover:text-accent-700">
                          {r.name}
                        </span>
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
                      {rowAction && (
                        <td
                          className="px-3 py-2.5 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {(() => {
                            const a = resolveAsset(r.id);
                            return a ? rowAction(a) : null;
                          })()}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Reveal>

      {/* 4 — analytics panels: composition donut + VAN bars + portfolio curve + revenue bars. */}
      <div className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          Análisis de cartera
        </h3>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <Reveal className="surface surface-hover p-4">
            <PanelTitle
              title="Composición de cartera"
              subtitle="Peso de cada activo sobre el VAN positivo total"
            />
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
                      stroke={ct.sliceStroke}
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
            {/* Legend — sober, theme-shared chips. */}
            {compositionData.length > 0 && (
              <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-slate-500">
                {compositionData.slice(0, 6).map((d, i) => (
                  <li key={d.name} className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-sm"
                      style={{ backgroundColor: DONUT[i % DONUT.length] }}
                      aria-hidden
                    />
                    <span className="max-w-[10rem] truncate">{d.name}</span>
                    <span className="tabular-nums text-slate-400">
                      {pct(compositionTotal ? d.value / compositionTotal : 0)}
                    </span>
                  </li>
                ))}
                {compositionData.length > 6 && (
                  <li className="text-slate-400">
                    +{compositionData.length - 6} más
                  </li>
                )}
              </ul>
            )}
          </Reveal>

          <Reveal className="surface surface-hover p-4" delay={60}>
            <PanelTitle
              title="VAN por activo"
              subtitle="Contribución de cada activo al valor de la cartera"
            />
            <div className="h-72 w-full">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ left: 8, right: 16 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} horizontal={false} />
                    <XAxis
                      type="number"
                      tickFormatter={(v: number) => eur(Number(v))}
                      fontSize={11}
                      stroke={ct.axisStroke}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      fontSize={11}
                      stroke={ct.axisStroke}
                      width={140}
                    />
                    <Tooltip
                      formatter={(v: number) => eur(Number(v))}
                      contentStyle={tooltipStyle}
                      cursor={{ fill: cursorFill }}
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

        {/* Consolidated portfolio curve — aggregated annual generation +
            cumulative trajectory across the included assets, over the horizon. */}
        <Reveal className="surface surface-hover p-4" delay={60}>
          <PanelTitle
            title="Curva consolidada de cartera"
            subtitle="Generación anual agregada y trayectoria acumulada, sobre el horizonte de proyección"
            right={
              portfolioCurve.length >= 2 ? (
                <span className="text-[11px] tabular-nums text-slate-400">
                  {portfolioCurve.length} años
                </span>
              ) : null
            }
          />
          <PortfolioCurve series={portfolioCurve} loading={seriesLoading} />
        </Reveal>

        {/* Año-1 revenue per asset — kept with the analytics, before the table. */}
        {revChartData.length > 0 && (
          <Reveal className="surface surface-hover p-4" delay={90}>
            <PanelTitle
              title="Ingresos año 1 por activo"
              subtitle="Primer año de explotación, por activo"
            />
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={revChartData}
                  layout="vertical"
                  margin={{ left: 8, right: 16 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} horizontal={false} />
                  <XAxis
                    type="number"
                    tickFormatter={(v: number) => eur(Number(v))}
                    fontSize={11}
                    stroke={ct.axisStroke}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    fontSize={11}
                    stroke={ct.axisStroke}
                    width={140}
                  />
                  <Tooltip
                    formatter={(v: number) => eur(Number(v))}
                    contentStyle={tooltipStyle}
                    cursor={{ fill: cursorFill }}
                  />
                  <Bar dataKey="revenue_y1" name="Ingresos año 1" fill={REV_BAR} radius={[0, 4, 4, 0]} animationDuration={800} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Reveal>
        )}
      </div>

      {/* 5 — map last (Cartera passes the operational map here). */}
      {mapSlot}
    </div>
  );
}
