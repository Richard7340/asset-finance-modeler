import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Consolidado } from "../api";
import { eur } from "../format";
import { useChartTheme } from "../hooks/useChartTheme";

type Vista = "resultado" | "caja" | "deuda";

/**
 * La cartera entera en el tiempo, por AÑO NATURAL (cada activo desde que
 * empieza): ingresos y EBITDA, el flujo de caja con su acumulado, o la deuda
 * viva. Una línea marca el año en curso: a la izquierda lo ya vivido, a la
 * derecha lo previsto (28-sep).
 */
export default function ConsolidadoChart({ data }: { data: Consolidado }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const [vista, setVista] = useState<Vista>("resultado");
  const hoy = new Date().getFullYear();

  const filas = useMemo(() => {
    let acc = 0;
    return data.years.map((y, i) => {
      acc += data.flujo_caja[i] ?? 0;
      return {
        anio: String(y),
        ingresos: data.revenue[i] ?? 0,
        ebitda: data.ebitda[i] ?? 0,
        beneficio: data.net_income[i] ?? 0,
        flujo: data.flujo_caja[i] ?? 0,
        acumulado: acc,
        deuda: data.deuda[i] ?? 0,
      };
    });
  }, [data]);

  if (filas.length < 2) {
    return (
      <div className="grid h-72 place-items-center px-6 text-center text-xs text-slate-400">
        Aún no hay suficientes años para dibujar la curva de la cartera.
      </div>
    );
  }

  const botones: Array<[Vista, string]> = [
    ["resultado", "Ingresos y EBITDA"],
    ["caja", "Flujo de caja"],
    ["deuda", "Deuda viva"],
  ];
  const hayDeuda = filas.some((f) => f.deuda > 0);

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {botones
          .filter(([v]) => v !== "deuda" || hayDeuda)
          .map(([v, t]) => (
            <button
              key={v}
              type="button"
              onClick={() => setVista(v)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                vista === v
                  ? "border-accent-500 bg-accent-50 text-accent-700"
                  : "border-slate-200 text-slate-500 hover:text-slate-700"
              }`}
            >
              {t}
            </button>
          ))}
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={filas} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke={ct.grid} vertical={false} />
            <XAxis dataKey="anio" tick={AXIS} stroke={ct.axisStroke} interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => eur(v)} width={78} />
            <Tooltip contentStyle={ct.tooltip} formatter={(v: number, n: string) => [eur(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine x={String(hoy)} stroke="#f59e0b" strokeDasharray="4 3" label={{ value: "hoy", position: "top", fontSize: 10, fill: "#f59e0b" }} />
            <ReferenceLine y={0} stroke={ct.zeroLine} />
            {/* Recharts no mira dentro de fragmentos: cada serie, suelta. */}
            {vista === "resultado" && <Bar dataKey="ingresos" name="Ingresos" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={26} />}
            {vista === "resultado" && <Line dataKey="ebitda" name="EBITDA" stroke="#10b981" strokeWidth={2.2} dot={false} />}
            {vista === "resultado" && <Line dataKey="beneficio" name="Beneficio neto" stroke="#0ea5e9" strokeWidth={1.6} strokeDasharray="5 3" dot={false} />}
            {vista === "caja" && <Bar dataKey="flujo" name="Flujo de caja del año" fill="#0ea5e9" radius={[3, 3, 0, 0]} maxBarSize={26} />}
            {vista === "caja" && <Line dataKey="acumulado" name="Acumulado" stroke="#4f46e5" strokeWidth={2.2} dot={false} />}
            {vista === "deuda" && <Area dataKey="deuda" name="Deuda viva" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.15} strokeWidth={2} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
