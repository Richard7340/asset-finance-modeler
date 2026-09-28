import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getLines, getSerie } from "../../api";
import type { Cada } from "../../api";
import { eur } from "../../format";
import { useChartTheme } from "../../hooks/useChartTheme";
import { Dato } from "./DeudaPanel";

const CADAS: Array<[Cada, string]> = [["dia", "Día"], ["semana", "Semana"], ["mes", "Mes"], ["anio", "Año"]];

/**
 * Lo real frente a lo previsto, con la frecuencia que cada uno anota (28-sep):
 * producción diaria de una planta, ventas semanales de un restaurante, rentas
 * mensuales de un piso… Barras = lo real de cada periodo; línea = lo que
 * tocaba según el modelo; y los acumulados para ver si el año va o no va.
 */
export default function SerieRealPanel({ assetId }: { assetId: string }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const lines = useQuery({ queryKey: ["lines", assetId], queryFn: () => getLines(assetId) });
  const opciones = useMemo(() => {
    const ls = lines.data ?? [];
    // Primero lo que más se sigue: producción, ingresos, cada línea; los agregados contables al final.
    const peso = (p: string) => (p.includes("produccion") ? 0 : p.endsWith(".revenue") ? 1 : p.startsWith("lineas.") ? 2 : 3);
    return [...ls].sort((a, b) => peso(a.path) - peso(b.path));
  }, [lines.data]);
  const [linea, setLinea] = useState<string>("");
  useEffect(() => { if (!linea && opciones.length) setLinea(opciones[0].path); }, [opciones, linea]);
  const [cada, setCada] = useState<Cada>("mes");
  const serie = useQuery({
    queryKey: ["serie", assetId, linea, cada],
    queryFn: () => getSerie(assetId, linea, cada),
    enabled: !!linea,
    placeholderData: (prev) => prev,
  });
  const unidad = opciones.find((o) => o.path === linea)?.unit ?? "";
  const fmt = (v: number) => (unidad ? `${Math.round(v).toLocaleString("es-ES")} ${unidad}` : eur(v));
  const s = serie.data;
  const datos = (s?.puntos ?? []).map((p) => ({ ...p, prevision: p.prevision }));
  const c = s?.resumen.cumplimiento_pct;

  if (lines.isLoading) return <div className="grid h-40 place-items-center text-sm text-slate-400">Cargando…</div>;
  if (!opciones.length) return <div className="grid h-40 place-items-center text-sm text-slate-400">Este activo no tiene líneas que seguir.</div>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={linea} onChange={(e) => setLinea(e.target.value)} className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-800 dark:bg-slate-900 dark:text-slate-100">
          {opciones.map((o) => <option key={o.path} value={o.path}>{o.label}{o.unit ? ` (${o.unit})` : ""}</option>)}
        </select>
        <div className="flex gap-1 rounded-lg border border-slate-200 p-0.5">
          {CADAS.map(([k, n]) => (
            <button key={k} type="button" onClick={() => setCada(k)} className={`rounded-md px-3 py-1 text-xs font-medium transition ${cada === k ? "bg-accent-50 text-accent-700" : "text-slate-500 hover:text-slate-700"}`}>{n}</button>
          ))}
        </div>
        {serie.isFetching && <span className="text-xs text-accent-600">cargando…</span>}
      </div>
      {s && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Dato label="Real de los periodos con dato" valor={s.resumen.real != null ? fmt(s.resumen.real) : "—"} />
          <Dato label="Previsto en esos periodos" valor={fmt(s.resumen.prevision_de_esos_periodos)} />
          <Dato label="Cumplimiento" valor={c != null ? `${c.toLocaleString("es-ES")} %` : "—"} tono={c == null ? undefined : c >= 100 ? "bien" : c >= 90 ? "justo" : "mal"} />
          <Dato label="Periodos con dato" valor={`${s.resumen.periodos_con_dato} de ${s.puntos.length}`} pista={s.resumen.periodos_con_dato < s.puntos.length ? "anota los que faltan para ver la foto completa" : undefined} />
        </div>
      )}
      <div className="surface p-4">
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={datos} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="etiqueta" tick={AXIS} stroke={ct.axisStroke} interval="preserveStartEnd" minTickGap={18} />
              <YAxis tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => fmt(v)} width={86} />
              <Tooltip contentStyle={ct.tooltip} formatter={(v: number, n: string) => [v == null ? "sin dato" : fmt(v), n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="real" name="Real" fill="#10b981" radius={[3, 3, 0, 0]} maxBarSize={22} />
              <Line dataKey="prevision" name="Previsto" stroke="#6366f1" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="surface p-4">
        <div className="mb-2 text-sm font-semibold text-slate-800">Acumulado</div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={datos} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="etiqueta" tick={AXIS} stroke={ct.axisStroke} interval="preserveStartEnd" minTickGap={18} />
              <YAxis tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => fmt(v)} width={86} />
              <Tooltip contentStyle={ct.tooltip} formatter={(v: number, n: string) => [fmt(v), n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line dataKey="acumulado_prevision" name="Previsto acumulado" stroke="#6366f1" strokeWidth={2} strokeDasharray="5 3" dot={false} />
              <Line dataKey="acumulado_real" name="Real acumulado" stroke="#10b981" strokeWidth={2.4} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          La previsión de cada periodo es la del año repartida por meses según {s?.estacionalidad ? <b>{s.estacionalidad}</b> : "la estacionalidad"} (cámbiala pidiéndoselo a tu agente: «en agosto vendemos el doble»). Los datos reales se anotan abajo o pidiéndoselo a tu agente: «apunta 250 MWh de hoy».
        </p>
      </div>
    </div>
  );
}
