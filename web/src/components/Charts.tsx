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
import type { RunResult } from "../api";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3>
      <div className="h-64 w-full">{children}</div>
    </div>
  );
}

const fmtK = (v: number) => `${Math.round(v / 1000)}k`;

export default function Charts({ data }: { data: RunResult }) {
  const cashflows = data.cashflows.years.map((year, i) => ({
    year,
    fv: data.cashflows.fv[i],
    bess: data.cashflows.bess[i],
  }));

  const curves = data.curves.spread.map((spread, i) => ({
    year: i + 1,
    spread,
    ancillary: data.curves.ancillary[i],
  }));

  const bridge = [
    { name: "FV", value: data.bridge.fv },
    { name: "BESS", value: data.bridge.bess },
    { name: "Híbrido", value: data.bridge.hybrid },
  ];

  const dscr = data.dscr_profile.map((v, i) => ({ year: i + 1, dscr: v }));

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Cashflows por año (FV vs BESS)">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={cashflows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
            <YAxis tickFormatter={fmtK} fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} />
            <Legend />
            <Bar dataKey="fv" name="FV" fill="#6366f1" />
            <Bar dataKey="bess" name="BESS" fill="#10b981" />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Curvas de mercado (30 años)">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curves}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" fontSize={11} stroke="#94a3b8" />
            <YAxis fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="spread"
              name="Spread capture"
              stroke="#6366f1"
              dot={false}
              strokeWidth={2}
            />
            <Line
              type="monotone"
              dataKey="ancillary"
              name="Ancillary"
              stroke="#f59e0b"
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Bridge NPV (FV → BESS → Híbrido)">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bridge}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="name" fontSize={11} stroke="#94a3b8" />
            <YAxis tickFormatter={fmtK} fontSize={11} stroke="#94a3b8" width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} />
            <ReferenceLine y={0} stroke="#cbd5e1" />
            <Bar dataKey="value" name="NPV">
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
            <Tooltip formatter={(v: number) => `${v.toFixed(2)}×`} />
            <ReferenceLine y={1} stroke="#f43f5e" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="dscr"
              name="DSCR"
              stroke="#6366f1"
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </Panel>
    </div>
  );
}
