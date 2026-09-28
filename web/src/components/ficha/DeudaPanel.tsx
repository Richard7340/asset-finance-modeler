import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Deuda } from "../../api";
import { eur, eurExact, mult } from "../../format";
import { useChartTheme } from "../../hooks/useChartTheme";

/**
 * La deuda del activo año a año (28-sep): lo que se paga (intereses y
 * amortización), cómo baja el saldo y el DSCR (cuántas veces cubre la caja
 * lo que hay que pagar: por debajo de 1,2× los bancos se ponen nerviosos).
 */
export default function DeudaPanel({ deuda, inicio }: { deuda: Deuda; inicio?: number }) {
  const ct = useChartTheme();
  const AXIS = { fontSize: 11, fill: ct.axis };
  const filas = deuda.years.map((y, i) => ({
    anio: inicio ? String(inicio + y - 1) : `A${y}`,
    intereses: deuda.intereses[i] ?? 0,
    amortizacion: deuda.amortizacion[i] ?? 0,
    saldo: deuda.saldo[i] ?? 0,
    dscr: deuda.dscr[i] ?? null,
  }));
  const total = (xs: number[]) => xs.reduce((a, b) => a + (b ?? 0), 0);
  const dscrs = deuda.dscr.filter((x): x is number => x != null && Number.isFinite(x));
  const dscrMin = dscrs.length ? Math.min(...dscrs) : null;
  const finPago = (() => { for (let i = deuda.saldo.length - 1; i >= 0; i -= 1) if ((deuda.saldo[i] ?? 0) > 0.5) return i + 1; return 0; })();
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Dato label="Deuda pedida" valor={eur(total(deuda.disposiciones))} />
        <Dato label="Intereses totales" valor={eur(total(deuda.intereses))} />
        <Dato label="DSCR mínimo" valor={dscrMin != null ? mult(dscrMin) : "—"} tono={dscrMin == null ? undefined : dscrMin >= 1.3 ? "bien" : dscrMin >= 1.1 ? "justo" : "mal"} />
        <Dato label="Se termina de pagar" valor={finPago ? (inicio ? String(inicio + finPago - 1) : `año ${finPago}`) : "—"} />
      </div>
      <div className="surface p-4">
        <div className="mb-2 text-sm font-semibold text-slate-800">Pagos del año y saldo pendiente</div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={filas} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="anio" tick={AXIS} stroke={ct.axisStroke} interval="preserveStartEnd" minTickGap={14} />
              <YAxis yAxisId="e" tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => eur(v)} width={78} />
              <YAxis yAxisId="x" orientation="right" tick={AXIS} stroke={ct.axisStroke} tickFormatter={(v: number) => `${v.toFixed(1)}×`} width={44} />
              <Tooltip contentStyle={ct.tooltip} formatter={(v: number, n: string) => [n === "DSCR" ? mult(v) : eur(v), n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="e" dataKey="intereses" name="Intereses" stackId="p" fill="#f59e0b" maxBarSize={26} />
              <Bar yAxisId="e" dataKey="amortizacion" name="Amortización" stackId="p" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={26} />
              <Line yAxisId="e" dataKey="saldo" name="Saldo pendiente" stroke="#f43f5e" strokeWidth={2.2} dot={false} />
              <Line yAxisId="x" dataKey="dscr" name="DSCR" stroke="#10b981" strokeWidth={1.8} strokeDasharray="5 3" dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="surface overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2 font-medium">Año</th>
              <th className="px-3 py-2 text-right font-medium">Disposición</th>
              <th className="px-3 py-2 text-right font-medium">Intereses</th>
              <th className="px-3 py-2 text-right font-medium">Amortización</th>
              <th className="px-3 py-2 text-right font-medium">Saldo al cierre</th>
              <th className="px-3 py-2 text-right font-medium">DSCR</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f, i) => (
              <tr key={f.anio} className="border-b border-slate-100 last:border-0">
                <td className="px-3 py-1.5 text-slate-600">{f.anio}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{deuda.disposiciones[i] ? eurExact(deuda.disposiciones[i]) : "—"}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{eurExact(f.intereses)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{eurExact(f.amortizacion)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums font-medium">{eurExact(f.saldo)}</td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${f.dscr == null ? "text-slate-400" : f.dscr < 1.1 ? "text-rose-600" : f.dscr < 1.3 ? "text-amber-600" : "text-emerald-600"}`}>{f.dscr == null ? "—" : mult(f.dscr)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Dato({ label, valor, tono, pista }: { label: string; valor: string; tono?: "bien" | "justo" | "mal"; pista?: string }) {
  const c = tono === "bien" ? "text-emerald-600" : tono === "justo" ? "text-amber-600" : tono === "mal" ? "text-rose-600" : "text-slate-800";
  return (
    <div className="surface p-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${c}`}>{valor}</div>
      {pista && <div className="mt-0.5 text-[11px] text-slate-400">{pista}</div>}
    </div>
  );
}
