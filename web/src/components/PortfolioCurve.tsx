import { useMemo } from "react";
import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { eur } from "../format";
import { useChartTheme } from "../hooks/useChartTheme";

const ACCENT = "#4f46e5";

type Props = {
  /** Consolidated annual series across the included assets (one value/year). */
  series: number[];
  /** Whether per-asset series are still loading (shows a hint). */
  loading?: boolean;
};

/**
 * Portfolio-level consolidated curve: the aggregated annual cash generation
 * across the whole portfolio (summed net income / CFO of the included assets)
 * plus its cumulative trajectory. This is the "whole portfolio at a glance over
 * time" view — the consolidated NAV build-up a CEO reads to feel in control.
 *
 * The series is derived client-side from each asset's stored result snapshot
 * (no backend change). When an asset's snapshot carries no readable series it
 * simply does not contribute; the curve still reflects everything that does.
 */
export default function PortfolioCurve({ series, loading }: Props) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };

  const data = useMemo(() => {
    let cum = 0;
    return series.map((annual, i) => {
      cum += annual;
      return { year: `A${i + 1}`, annual, cum };
    });
  }, [series]);

  if (series.length < 2) {
    return (
      <div className="grid h-72 place-items-center px-6 text-center text-xs text-slate-400">
        {loading
          ? "Cargando series de los activos…"
          : "Las series temporales de los activos no están disponibles para esta selección."}
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="portfolioCum" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.22} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
          <XAxis dataKey="year" tick={AXIS} stroke={ct.axisStroke} />
          <YAxis
            yAxisId="left"
            tickFormatter={(v: number) => eur(Number(v))}
            tick={AXIS}
            stroke={ct.axisStroke}
            width={64}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(v: number) => eur(Number(v))}
            tick={AXIS}
            stroke={ct.axisStroke}
            width={64}
          />
          <Tooltip
            formatter={(v: number, n: string) => [
              eur(Number(v)),
              n === "cum" ? "Acumulado" : "Generación anual",
            ]}
            labelFormatter={(l) => `Año ${String(l).replace("A", "")}`}
            contentStyle={ct.tooltip}
          />
          <ReferenceLine yAxisId="left" y={0} stroke={ct.zeroLine} />
          <Area
            yAxisId="right"
            type="monotone"
            dataKey="cum"
            name="cum"
            stroke={ACCENT}
            strokeWidth={2}
            fill="url(#portfolioCum)"
            dot={false}
            animationDuration={900}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="annual"
            name="annual"
            stroke={ct.dark ? "#e2e8f0" : "#0b1220"}
            strokeWidth={2}
            dot={false}
            animationDuration={900}
          />
        </ComposedChart>
      </ResponsiveContainer>
      {/* Legend — sober chips. */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ backgroundColor: ct.dark ? "#e2e8f0" : "#0b1220" }} />
          Generación anual (izq.)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ backgroundColor: ACCENT }} />
          Acumulado (der.)
        </span>
      </div>
    </div>
  );
}
