import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
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
function devClass(v: number | null, gasto = false): string {
  if (v == null || v === 0) return "text-slate-600";
  // En un gasto, pasarse de lo previsto es malo (27-sep: salia en verde).
  return (gasto ? v < 0 : v > 0) ? "text-emerald-700" : "text-rose-700";
}

/** ¿Es una línea de gasto? (IBI, suministros, OPEX…): ahí gastar más es peor. */
export function esLineaDeGasto(line: { line_path: string; label: string }): boolean {
  return /gasto|opex|cogs|cost|coste|capex|interes|impuest|tax/i.test(`${line.line_path} ${line.label}`);
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
            <span className={devClass(line.fulfillment_pct != null ? line.fulfillment_pct - 1 : null, esLineaDeGasto(line))}>
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
              // El año en curso se compara con lo previsto HASTA HOY, no con el año entero.
              const enCurso = line.anio_en_curso === i && line.fraccion_del_anio != null && line.fraccion_del_anio < 1;
              const comparada = line.base_comparada?.[i];
              return (
                <tr key={i} className={`border-b border-slate-100 ${enCurso ? "bg-indigo-50/40" : ""}`}>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-500">
                    A{i + 1}
                    {enCurso && (
                      <span className="ml-1 text-[10px] text-indigo-600" title="Comparado con lo previsto hasta hoy">
                        en curso · {fmtPct(line.fraccion_del_anio)}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-700">
                    {enCurso && av != null && comparada != null ? (
                      <span title={`Año entero: ${fmtNum(b)}`}>{fmtNum(comparada)}</span>
                    ) : (
                      fmtNum(b)
                    )}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-900">
                    {av == null ? "—" : fmtNum(av)}
                  </td>
                  <td className={`py-1.5 pr-2 text-right tabular-nums ${devClass(line.deviation[i], esLineaDeGasto(line))}`}>
                    {fmtNum(line.deviation[i])}
                  </td>
                  <td className={`py-1.5 pr-2 text-right tabular-nums ${devClass(line.deviation_pct[i], esLineaDeGasto(line))}`}>
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

      {line.mensual && line.mensual.some((m) => m.real != null) && <MesAMes line={line} unit={unit} />}

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

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** Mes a mes del año en curso: lo real frente a la previsión mensual (27-sep). */
function MesAMes({ line, unit }: { line: VarianceLine; unit: string }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const meses = line.mensual ?? [];
  const datos = meses.map((m) => ({ mes: MESES[m.mes - 1], prevision: m.prevision, real: m.real }));
  let acumReal = 0;
  let acumPrev = 0;
  return (
    <div className="mt-4">
      <div className="mb-1 text-xs font-semibold text-slate-700">Este año, mes a mes</div>
      <div className="h-40 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={datos} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
            <XAxis dataKey="mes" tick={AXIS} stroke={ct.axisStroke} interval={0} />
            <YAxis tick={AXIS} stroke={ct.axisStroke} width={52} />
            <Tooltip
              contentStyle={ct.tooltip}
              formatter={(v: number, name: string) => [v == null ? "—" : `${fmtNum(v)}${unit}`, name === "prevision" ? "Previsto" : "Real"]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v) => (v === "prevision" ? "Previsto" : "Real")} />
            <Bar dataKey="prevision" fill={C.base} fillOpacity={0.35} isAnimationActive={false} />
            <Bar dataKey="real" fill={actualColor(ct)} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-400">
              <th className="py-1 pr-2 font-medium">Mes</th>
              <th className="py-1 pr-2 text-right font-medium">Previsto</th>
              <th className="py-1 pr-2 text-right font-medium">Real</th>
              <th className="py-1 pr-2 text-right font-medium">Diferencia</th>
              <th className="py-1 pr-2 text-right font-medium">Acum. dif.</th>
            </tr>
          </thead>
          <tbody>
            {meses.filter((m) => m.real != null).map((m) => {
              const dif = (m.real as number) - m.prevision;
              acumReal += m.real as number;
              acumPrev += m.prevision;
              return (
                <tr key={m.mes} className="border-b border-slate-100">
                  <td className="py-1 pr-2 text-slate-500">{MESES[m.mes - 1]}</td>
                  <td className="py-1 pr-2 text-right tabular-nums text-slate-700">{fmtNum(m.prevision)}</td>
                  <td className="py-1 pr-2 text-right tabular-nums text-slate-900">{fmtNum(m.real)}</td>
                  <td className={`py-1 pr-2 text-right tabular-nums ${devClass(dif, esLineaDeGasto(line))}`}>{fmtNum(dif)}</td>
                  <td className={`py-1 pr-2 text-right tabular-nums ${devClass(acumReal - acumPrev, esLineaDeGasto(line))}`}>{fmtNum(acumReal - acumPrev)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-slate-400">Previsto: la previsión del año repartida por igual entre los meses.</p>
    </div>
  );
}
