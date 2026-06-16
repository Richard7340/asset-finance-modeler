import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getVariance } from "../api";
import type { VarianceLine } from "../api";
import { useChartTheme } from "../hooks/useChartTheme";
import type { ChartTheme } from "../hooks/useChartTheme";

type Props = { assetId: string };

// Sober palette: a muted indigo for base, a neutral series for real points
// (which flips to a light tone on the dark ink surface).
const C = {
  base: "#6366f1",
  actual: "#0f172a",
};

function fmtNum(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("es-ES", { maximumFractionDigits: 0 });
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toLocaleString("es-ES", { maximumFractionDigits: 1 })}%`;
}

/** Sober colour cue for a deviation: green when ahead of base, red when behind. */
function devClass(v: number | null): string {
  if (v == null || v === 0) return "text-slate-600";
  return v > 0 ? "text-emerald-700" : "text-rose-700";
}

/**
 * "Varianza real-vs-base" — for each trackable line, a table (year · base ·
 * real · deviation · % · cumulative · fulfilment) and a chart overlaying the
 * frozen base line with the real points. No reprojection (that is F3).
 */
export default function VariancePanel({ assetId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["variance", assetId],
    queryFn: () => getVariance(assetId),
  });

  if (isLoading) {
    return <div className="p-2 text-sm text-slate-400">Cargando varianza…</div>;
  }
  if (error || !data) {
    return (
      <div className="p-2 text-sm text-slate-400">
        No se pudo cargar la varianza.
      </div>
    );
  }

  // Only show lines that have at least one real data point — keeps the panel
  // focused on lines actually being tracked.
  const tracked = data.lines.filter((l) => l.actual.some((v) => v != null));

  return (
    <section className="surface p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">
          Varianza real vs base
        </h3>
        <span className="text-[11px] text-slate-400">Caso base congelado</span>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Desviación del dato real frente al caso base por año. Sin reproyección de
        la valoración.
      </p>

      {tracked.length === 0 ? (
        <div className="p-2 text-xs text-slate-400">
          Aún no hay datos reales registrados. Añádelos arriba para ver la
          desviación.
        </div>
      ) : (
        <div className="space-y-6">
          {tracked.map((line) => (
            <LineVariance key={line.line_path} line={line} />
          ))}
        </div>
      )}
    </section>
  );
}

/** The realised points need a light marker to read on the dark ink surface. */
function actualColor(ct: ChartTheme): string {
  return ct.dark ? "#e2e8f0" : C.actual;
}

function LineVariance({ line }: { line: VarianceLine }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const tooltipStyle = ct.tooltip;
  const [openChart, setOpenChart] = useState(true);
  const unit = line.unit ? ` ${line.unit}` : "";

  const chartData = line.base.map((b, i) => ({
    year: i + 1,
    base: b,
    actual: line.actual[i],
  }));

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-800" title={line.line_path}>
            {line.label}
          </div>
          <div className="text-[11px] text-slate-400">
            Cumplimiento acumulado:{" "}
            <span className={devClass(line.fulfillment_pct != null ? line.fulfillment_pct - 1 : null)}>
              {fmtPct(line.fulfillment_pct)}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpenChart((o) => !o)}
          aria-pressed={openChart}
          className="rounded border border-slate-300 px-2 py-0.5 text-[11px] text-slate-600 transition hover:bg-slate-50"
        >
          {openChart ? "Ocultar gráfico" : "Ver gráfico"}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-400">
              <th className="py-1.5 pr-2 font-medium">Año</th>
              <th className="py-1.5 pr-2 text-right font-medium">Base</th>
              <th className="py-1.5 pr-2 text-right font-medium">Real</th>
              <th className="py-1.5 pr-2 text-right font-medium">Desviación</th>
              <th className="py-1.5 pr-2 text-right font-medium">%</th>
            </tr>
          </thead>
          <tbody>
            {line.base.map((b, i) => {
              const av = line.actual[i];
              return (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1.5 pr-2 tabular-nums text-slate-500">A{i + 1}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-700">
                    {fmtNum(b)}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-900">
                    {av == null ? "—" : fmtNum(av)}
                  </td>
                  <td className={`py-1.5 pr-2 text-right tabular-nums ${devClass(line.deviation[i])}`}>
                    {fmtNum(line.deviation[i])}
                  </td>
                  <td className={`py-1.5 pr-2 text-right tabular-nums ${devClass(line.deviation_pct[i])}`}>
                    {fmtPct(line.deviation_pct[i])}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-slate-300 text-[11px] font-medium text-slate-700">
              <td className="py-1.5 pr-2">Acum.</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{fmtNum(line.cumulative_base)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{fmtNum(line.cumulative_actual)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {fmtNum(line.cumulative_actual - line.cumulative_base)}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{fmtPct(line.fulfillment_pct)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {openChart && (
        <div className="mt-3 h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
              <XAxis dataKey="year" tick={AXIS} stroke={ct.axisStroke} interval={0} />
              <YAxis tick={AXIS} stroke={ct.axisStroke} width={52} />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v: number, name: string) => [
                  v == null ? "—" : `${fmtNum(v)}${unit}`,
                  name === "base" ? "Base" : "Real",
                ]}
                labelFormatter={(l) => `Año ${l}`}
              />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                formatter={(value) => (value === "base" ? "Base" : "Real")}
              />
              <Line
                type="monotone"
                dataKey="base"
                stroke={C.base}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Scatter dataKey="actual" fill={actualColor(ct)} line={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
