import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { eur } from "../../format";
import { useChartTheme } from "../../hooks/useChartTheme";

const COLORES = ["#6366f1", "#10b981", "#f59e0b", "#0ea5e9", "#ec4899", "#8b5cf6", "#14b8a6", "#f43f5e", "#84cc16", "#64748b"];

type Lineas = { ingresos?: Record<string, number[]>; gastos?: Record<string, number[]>; produccion?: Record<string, number[]> };

/**
 * Cada ingreso, cada gasto y la producción por separado, año a año (28-sep):
 * las curvas que el usuario o su agente han puesto (curva propia, subidas
 * año a año, IPC, degradación, repowering…) se ven aquí tal cual.
 */
export default function LineasChart({ lineas }: { lineas: Lineas }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const grupos = (["ingresos", "gastos", "produccion"] as const).filter((g) => Object.keys(lineas[g] ?? {}).length);
  const [grupo, setGrupo] = useState<(typeof grupos)[number]>(grupos[0] ?? "ingresos");
  const series = lineas[grupo] ?? {};
  const nombres = Object.keys(series).slice(0, 10);
  const datos = useMemo(() => {
    const n = Math.max(0, ...nombres.map((k) => series[k]?.length ?? 0));
    return Array.from({ length: n }, (_, i) => ({ anio: `A${i + 1}`, ...Object.fromEntries(nombres.map((k) => [k, series[k]?.[i] ?? null])) }));
  }, [series, nombres]);
  if (!grupos.length) return null;
  const esMwh = grupo === "produccion";
  const fmt = (v: number) => (esMwh ? `${Math.round(v).toLocaleString("es-ES")} MWh` : eur(v));
  const nombreGrupo = { ingresos: "Ingresos", gastos: "Gastos", produccion: "Producción" } as const;
  return (
    <div className="surface p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-800">Línea a línea</div>
          <div className="text-[11px] text-slate-400">Cada {esMwh ? "producción" : grupo === "ingresos" ? "ingreso" : "gasto"} con su curva, año a año</div>
        </div>
        <div className="flex gap-1">
          {grupos.map((g) => (
            <button key={g} type="button" onClick={() => setGrupo(g)} className={`rounded-full border px-3 py-1 text-xs font-medium ${grupo === g ? "border-accent-500 bg-accent-50 text-accent-700" : "border-slate-200 text-slate-500"}`}>{nombreGrupo[g]}</button>
          ))}
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={datos} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke={ct.grid} vertical={false} />
            <XAxis dataKey="anio" tick={AXIS} stroke={ct.axisStroke} interval="preserveStartEnd" minTickGap={14} />
            <YAxis tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => fmt(v)} width={84} />
            <Tooltip contentStyle={ct.tooltip} formatter={(v: number, n: string) => [fmt(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {nombres.map((k, i) => <Line key={k} dataKey={k} stroke={COLORES[i % COLORES.length]} strokeWidth={2} dot={false} />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
