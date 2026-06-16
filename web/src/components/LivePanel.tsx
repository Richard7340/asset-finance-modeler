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
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { getLive } from "../api";
import type { LiveResult } from "../api";
import { eur, mult, pct } from "../format";
import AnimatedNumber from "./AnimatedNumber";

type Props = { assetId: string };

// Sober palette shared with VariancePanel: muted indigo for the base line,
// dark slate for the realised points, a dashed reprojection for the future.
const C = {
  base: "#94a3b8",
  reproj: "#6366f1",
  actual: "#0f172a",
  grid: "#eef2f7",
  slate: "#94a3b8",
};
const AXIS = { fontSize: 11, fill: "#64748b" };
const tooltipStyle = {
  fontSize: 12,
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  boxShadow: "0 6px 24px rgb(15 23 42 / 0.10)",
  padding: "8px 10px",
};

function fmtNum(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("es-ES", { maximumFractionDigits: 0 });
}

/** Sober colour cue: green when live is ahead of base, red when behind. */
function deltaClass(delta: number): string {
  if (!Number.isFinite(delta) || Math.abs(delta) < 1e-9) return "text-slate-500";
  return delta > 0 ? "text-emerald-700" : "text-rose-700";
}

/** A small, emoji-free up/down/flat indicator. */
function DeltaIcon({ delta }: { delta: number }) {
  if (!Number.isFinite(delta) || Math.abs(delta) < 1e-9) {
    return <Minus className="h-3.5 w-3.5" aria-label="sin cambio" />;
  }
  return delta > 0 ? (
    <ArrowUp className="h-3.5 w-3.5" aria-label="al alza" />
  ) : (
    <ArrowDown className="h-3.5 w-3.5" aria-label="a la baja" />
  );
}

/**
 * A base-vs-live KPI card: base value (muted) over live value (bold), with the
 * signed delta and a sober arrow.
 */
function CompareCard({
  label,
  base,
  live,
  format,
  delta,
  formatDelta,
}: {
  label: string;
  base: number;
  live: number;
  format: (n: number) => string;
  delta: number;
  formatDelta: (n: number) => string;
}) {
  return (
    <div className="surface relative overflow-hidden p-4">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <AnimatedNumber
          value={live}
          format={format}
          className="text-2xl font-semibold tabular-nums text-slate-900"
        />
        <span className={`flex items-center gap-0.5 text-xs font-medium ${deltaClass(delta)}`}>
          <DeltaIcon delta={delta} />
          {delta > 0 ? "+" : ""}
          {formatDelta(delta)}
        </span>
      </div>
      <div className="mt-0.5 text-xs text-slate-400">
        Base <span className="tabular-nums text-slate-500">{format(base)}</span>
        <span className="px-1">·</span>
        Live
      </div>
    </div>
  );
}

/**
 * "Reproyección viva (BASE vs LIVE)" — for an operational asset: head-to-head
 * KPI cards (VAN, TIR, DSCR mín) with deltas, plus a chart overlaying the frozen
 * base CFO line, the realised points to date, and the reprojected future
 * (dashed). The reprojection is an annual overlay (see core/live.py).
 */
export default function LivePanel({ assetId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["live", assetId],
    queryFn: () => getLive(assetId),
  });

  if (isLoading) {
    return <div className="p-2 text-sm text-slate-400">Cargando reproyección…</div>;
  }
  // A non-operational asset returns 422 — but App only renders this for
  // operational assets, so any error here is a genuine load failure.
  if (error || !data) {
    return (
      <div className="p-2 text-sm text-slate-400">
        No se pudo cargar la reproyección viva.
      </div>
    );
  }

  return (
    <section className="surface p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">
          Reproyección viva (base vs live)
        </h3>
        <span className="text-[11px] text-slate-400">
          {data.comparison.elapsed_years} de {data.comparison.n_years} años con dato real
        </span>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        El caso base congelado frente a la reproyección viva: reales en los años
        ya ocurridos y supuestos base en el futuro. Overlay anual.
      </p>

      <CompareCards data={data} />
      <LiveChart data={data} />
    </section>
  );
}

function CompareCards({ data }: { data: LiveResult }) {
  const c = data.comparison;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <CompareCard
        label="VAN"
        base={c.npv_base}
        live={c.npv_live}
        format={eur}
        delta={c.delta}
        formatDelta={eur}
      />
      <CompareCard
        label="TIR proyecto"
        base={c.irr_base}
        live={c.irr_live}
        format={pct}
        delta={c.irr_live - c.irr_base}
        formatDelta={pct}
      />
      <CompareCard
        label="DSCR mín"
        base={c.dscr_min_base}
        live={c.dscr_min_live}
        format={mult}
        delta={c.dscr_min_live - c.dscr_min_base}
        formatDelta={mult}
      />
    </div>
  );
}

/**
 * Overlay chart: frozen base CFO line, realised points to date (live CFO over
 * the elapsed years), and the reprojected future drawn dashed.
 */
function LiveChart({ data }: { data: LiveResult }) {
  const baseCfo = data.base.cash_flow.cfo;
  const liveCfo = data.live.cash_flow.cfo;
  const years = data.base.cash_flow.years;
  const elapsed = data.comparison.elapsed_years;

  const chartData = baseCfo.map((b, i) => {
    const past = i < elapsed;
    return {
      year: years[i] ?? i + 1,
      base: b,
      // Realised points only for elapsed years.
      actual: past ? liveCfo[i] : null,
      // Reprojected future (dashed) for the years from here on. Include the
      // boundary point so the dashed line connects to the last realised point.
      reproj: i >= elapsed - 1 ? liveCfo[i] : null,
    };
  });

  return (
    <div className="mt-4 h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
          <XAxis dataKey="year" tick={AXIS} stroke={C.slate} interval={0} />
          <YAxis tick={AXIS} stroke={C.slate} width={52} />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(v: number, name: string) => [
              v == null ? "—" : fmtNum(v),
              name === "base" ? "Base (CFO)" : name === "reproj" ? "Reproyección" : "Real",
            ]}
            labelFormatter={(l) => `Año ${l}`}
          />
          <Legend
            wrapperStyle={{ fontSize: 11 }}
            formatter={(value) =>
              value === "base" ? "Base (CFO)" : value === "reproj" ? "Reproyección" : "Real"
            }
          />
          <Line
            type="monotone"
            dataKey="base"
            stroke={C.base}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="reproj"
            stroke={C.reproj}
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Scatter dataKey="actual" fill={C.actual} line={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
