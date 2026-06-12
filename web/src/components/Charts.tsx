import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RunResult, IncomeStatement } from "../api";
import { isHybridResult } from "../api";
import { eur } from "../format";

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3>
      <div className="h-64 w-full">{children}</div>
    </div>
  );
}

const fmtK = (v: number) => `${Math.round(Number(v) / 1000)}k`;

/** Revenue vs EBITDA bar chart over years (generic infra/business). */
function RevenueEbitdaChart({ is }: { is: IncomeStatement }) {
  const data = is.years.map((year, i) => ({
    year: `A${year}`,
    revenue: is.rows.revenue[i] ?? 0,
    ebitda: is.rows.ebitda[i] ?? 0,
  }));
  return (
    <Panel title="Ingresos y EBITDA por año">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
          <YAxis tickFormatter={fmtK} fontSize={11} stroke="#94a3b8" width={56} />
          <Tooltip formatter={(v: number) => eur(Number(v))} contentStyle={{ fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" name="Ingresos" fill="#0ea5e9" />
          <Bar dataKey="ebitda" name="EBITDA" fill="#0f172a" />
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  );
}

/** Legacy svj_hybrid curves: cashflows, market curves, bridge, DSCR profile. */
function HybridCharts({ data }: { data: RunResult }) {
  const cashflows = (data.cashflows?.years ?? []).map((year, i) => ({
    year,
    fv: data.cashflows?.fv[i] ?? 0,
    bess: data.cashflows?.bess[i] ?? 0,
  }));

  const curves = (data.curves?.spread ?? []).map((spread, i) => ({
    year: i + 1,
    spread,
    ancillary: data.curves?.ancillary[i] ?? 0,
  }));

  const bridge = data.bridge
    ? [
        { name: "FV", value: data.bridge.fv },
        { name: "BESS", value: data.bridge.bess },
        { name: "Híbrido", value: data.bridge.hybrid },
      ]
    : [];

  const dscr = (data.dscr_profile ?? []).map((v, i) => ({ year: i + 1, dscr: v }));

  return (
    <>
      <Panel title="Cashflows por año (FV vs BESS)">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={cashflows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
            <YAxis tickFormatter={fmtK} fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} />
            <Legend />
            <Bar dataKey="fv" name="FV" fill="#0ea5e9" />
            <Bar dataKey="bess" name="BESS" fill="#0f172a" />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Curvas de mercado">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curves}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
            <YAxis fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="spread" name="Spread capture" stroke="#0ea5e9" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="ancillary" name="Ancillary" stroke="#f59e0b" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Bridge VAN (FV → BESS → Híbrido)">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bridge}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="name" fontSize={11} stroke="#94a3b8" />
            <YAxis tickFormatter={fmtK} fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} />
            <ReferenceLine y={0} stroke="#cbd5e1" />
            <Bar dataKey="value" name="VAN">
              {bridge.map((b) => (
                <Cell key={b.name} fill={b.value >= 0 ? "#10b981" : "#f43f5e"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Perfil DSCR (deuda subordinada)">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={dscr}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
            <YAxis fontSize={11} stroke="#94a3b8" width={48} domain={[0, "auto"]} />
            <Tooltip formatter={(v: number) => `${Number(v).toFixed(2)}×`} />
            <ReferenceLine y={1} stroke="#f43f5e" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="dscr" name="DSCR" stroke="#0ea5e9" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>
    </>
  );
}

export default function Charts({ data }: { data: RunResult }) {
  if (isHybridResult(data)) {
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <HybridCharts data={data} />
      </div>
    );
  }
  if (data.income_statement) {
    return (
      <div className="grid grid-cols-1 gap-4">
        <RevenueEbitdaChart is={data.income_statement} />
      </div>
    );
  }
  return null;
}
