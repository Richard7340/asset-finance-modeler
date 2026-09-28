import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getValoracion } from "../../api";
import { eur, pct } from "../../format";
import { useChartTheme } from "../../hooks/useChartTheme";
import { Dato } from "./DeudaPanel";

/**
 * Cuánto vale hoy el activo (28-sep): lo mismo que responde el agente a
 * «¿cuánto vale?». Flujos libres descontados más el valor final, lo que
 * queda para el dueño tras la deuda, un rango y la tabla tasa × crecimiento
 * para ver cuánto cambia si las hipótesis se mueven. Se puede tocar la tasa,
 * el crecimiento y la deuda y ver el resultado al momento.
 */
export default function ValoracionPanel({ assetId, deudaViva }: { assetId: string; deudaViva?: number | null }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const [tasa, setTasa] = useState<number | undefined>();
  const [g, setG] = useState<number | undefined>();
  const [deuda, setDeuda] = useState<number | undefined>(deudaViva ?? undefined);
  const q = useQuery({
    queryKey: ["valoracion", assetId, tasa, g, deuda],
    queryFn: () => getValoracion(assetId, { tasa, crecimiento: g, deuda_neta: deuda }),
    placeholderData: (prev) => prev,
  });
  const v = q.data;
  if (q.isLoading || !v) return <div className="grid h-40 place-items-center text-sm text-slate-400">Valorando…</div>;
  if (q.isError) return <div className="grid h-40 place-items-center text-sm text-rose-500">No se ha podido valorar este activo.</div>;

  const sens = v.sensibilidad;
  const todos = sens ? sens.valor_empresa.flat().filter(Number.isFinite) : [];
  const min = todos.length ? Math.min(...todos) : v.valor_empresa;
  const max = todos.length ? Math.max(...todos) : v.valor_empresa;
  const color = (x: number) => {
    const t = max === min ? 0.5 : (x - min) / (max - min);
    return `rgba(${Math.round(244 - t * 228)}, ${Math.round(63 + t * 122)}, ${Math.round(94 + t * 35)}, 0.22)`;
  };
  const flujos = v.flujos_libres.map((f, i) => ({ anio: `A${i + 1}`, flujo: f }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Dato label="Valor de la empresa" valor={eur(v.valor_empresa)} pista="lo que valen hoy sus flujos" />
        <Dato label="Valor para ti" valor={eur(v.valor_para_el_dueno)} pista={v.deuda_neta ? `tras ${eur(v.deuda_neta)} de deuda` : "sin deuda que restar"} tono={v.valor_para_el_dueno >= 0 ? "bien" : "mal"} />
        <Dato label="Rango razonable" valor={`${eur(min)} – ${eur(max)}`} pista="moviendo tasa y crecimiento" />
        <Dato label="Peso del valor final" valor={pct(v.peso_valor_terminal)} pista={v.peso_valor_terminal > 0.7 ? "mucho depende del largo plazo" : "equilibrado"} tono={v.peso_valor_terminal > 0.7 ? "justo" : undefined} />
      </div>

      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-end gap-4 text-xs text-slate-500">
          <Control label="Tasa de descuento" valor={tasa ?? v.tasa_descuento} min={0.03} max={0.2} paso={0.005} fmt={pct} onChange={setTasa} />
          <Control label="Crecimiento a largo plazo" valor={g ?? v.crecimiento_final} min={-0.02} max={0.05} paso={0.005} fmt={pct} onChange={setG} />
          <label className="flex flex-col gap-1">
            <span>Deuda neta a restar</span>
            <input type="number" step={1000} className="w-36 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm text-slate-800 dark:bg-slate-900 dark:text-slate-100" value={deuda ?? v.deuda_neta} onChange={(e) => setDeuda(Number(e.target.value))} />
          </label>
          {q.isFetching && <span className="text-accent-600">recalculando…</span>}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-1 text-sm font-semibold text-slate-800">De dónde sale el valor</div>
            <div className="text-[11px] text-slate-400">
              Flujos de los próximos {v.anios} años: {eur(v.dcf.vp_flujos)} · valor final: {eur(v.dcf.vp_valor_terminal)}
              {v.ev_ebitda_implicito ? ` · ${v.ev_ebitda_implicito.toLocaleString("es-ES")}× EBITDA` : ""}
            </div>
            <div className="mt-2 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flujos} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
                  <CartesianGrid stroke={ct.grid} vertical={false} />
                  <XAxis dataKey="anio" tick={AXIS} stroke={ct.axisStroke} />
                  <YAxis tick={AXIS} stroke={ct.axisStroke} tickFormatter={(x: number) => eur(x)} width={72} />
                  <Tooltip contentStyle={ct.tooltip} formatter={(x: number) => [eur(x), "Flujo libre"]} />
                  <Bar dataKey="flujo" radius={[3, 3, 0, 0]} maxBarSize={28}>
                    {flujos.map((f) => <Cell key={f.anio} fill={f.flujo >= 0 ? "#6366f1" : "#f43f5e"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          {sens && (
            <div>
              <div className="mb-1 text-sm font-semibold text-slate-800">Si cambian las hipótesis</div>
              <div className="text-[11px] text-slate-400">Valor de la empresa según la tasa (filas) y el crecimiento a largo plazo (columnas)</div>
              <table className="mt-2 w-full text-xs tabular-nums">
                <thead>
                  <tr>
                    <th className="p-1.5 text-left font-medium text-slate-400">tasa \ crec.</th>
                    {sens.crecimientos.map((c) => <th key={c} className="p-1.5 text-right font-medium text-slate-500">{pct(c)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {sens.tasas.map((t, i) => (
                    <tr key={t}>
                      <td className="p-1.5 font-medium text-slate-500">{pct(t)}</td>
                      {sens.valor_empresa[i].map((x, j) => {
                        const actual = Math.abs(t - (tasa ?? v.tasa_descuento)) < 1e-6 && Math.abs(sens.crecimientos[j] - (g ?? v.crecimiento_final)) < 1e-6;
                        return (
                          <td key={j} className={`p-1.5 text-right ${actual ? "font-bold text-slate-900 ring-2 ring-accent-500 ring-inset" : "text-slate-700"}`} style={{ background: color(x) }}>
                            {eur(x)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {!!v.notas?.length && (
          <ul className="mt-3 space-y-1 text-[11px] text-slate-400">
            {v.notas.map((n) => <li key={n}>· {n}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function Control({ label, valor, min, max, paso, fmt, onChange }: { label: string; valor: number; min: number; max: number; paso: number; fmt: (n: number) => string; onChange: (n: number) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span>{label}: <b className="text-slate-800">{fmt(valor)}</b></span>
      <input type="range" min={min} max={max} step={paso} value={valor} onChange={(e) => onChange(Number(e.target.value))} className="w-44 accent-accent-600" />
    </label>
  );
}
