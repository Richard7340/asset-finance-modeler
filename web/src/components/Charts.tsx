import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RunResult, IncomeStatement, CashFlow } from "../api";
import { isHybridResult } from "../api";
import { eur } from "../format";
import Reveal from "./Reveal";

// Cohesive palette: indigo accent primary, ink for the "net" series,
// emerald/rose strictly for +/- signal.
const C = {
  accent: "#4f46e5", // indigo-600
  accentSoft: "#818cf8", // indigo-400
  ink: "#0b1220",
  slate: "#94a3b8",
  grid: "#eef2f7",
  pos: "#10b981",
  neg: "#f43f5e",
  amber: "#f59e0b",
};

const AXIS = { fontSize: 11, fill: "#64748b" };

function Panel({
  title,
  subtitle,
  delay = 0,
  children,
}: {
  title: string;
  subtitle?: string;
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <Reveal delay={delay} className="surface surface-hover p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {subtitle && (
          <span className="text-[11px] text-slate-400">{subtitle}</span>
        )}
      </div>
      <div className="h-64 w-full">{children}</div>
    </Reveal>
  );
}

const fmtK = (v: number) => `${Math.round(Number(v) / 1000)}k`;

const tooltipStyle = {
  fontSize: 12,
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  boxShadow: "0 6px 24px rgb(15 23 42 / 0.10)",
  padding: "8px 10px",
};

/** Income statement as a chart: Ingresos / EBITDA bars + Beneficio neto line. */
function IncomeStatementChart({ is }: { is: IncomeStatement }) {
  const data = is.years.map((year, i) => ({
    year: `A${year}`,
    revenue: is.rows.revenue[i] ?? 0,
    ebitda: is.rows.ebitda[i] ?? 0,
    net: is.rows.net_income?.[i] ?? 0,
  }));
  return (
    <Panel title="Resultado por año" subtitle="Ingresos · EBITDA · Beneficio neto">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
          <XAxis dataKey="year" tick={AXIS} stroke={C.slate} />
          <YAxis tickFormatter={fmtK} tick={AXIS} stroke={C.slate} width={56} />
          <Tooltip formatter={(v: number) => eur(Number(v))} contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" name="Ingresos" fill={C.accent} radius={[3, 3, 0, 0]} maxBarSize={26} animationDuration={700} />
          <Bar dataKey="ebitda" name="EBITDA" fill={C.accentSoft} radius={[3, 3, 0, 0]} maxBarSize={26} animationDuration={700} />
          <Line type="monotone" dataKey="net" name="Beneficio neto" stroke={C.ink} strokeWidth={2} dot={{ r: 2 }} animationDuration={900} />
        </ComposedChart>
      </ResponsiveContainer>
    </Panel>
  );
}

/** Cash flow: CFO/CFI/CFF bars + FCF and CUMULATIVE FCF lines. */
function CashFlowChart({ cf }: { cf: CashFlow }) {
  let cum = 0;
  const data = cf.years.map((y, i) => {
    const fcf = (cf.cfo[i] ?? 0) + (cf.cfi[i] ?? 0);
    cum += fcf;
    return {
      year: `A${y}`,
      cfo: cf.cfo[i] ?? 0,
      cfi: cf.cfi[i] ?? 0,
      cff: cf.cff[i] ?? 0,
      fcf,
      cum,
    };
  });
  return (
    <Panel title="Flujos de caja" subtitle="CFO · CFI · CFF · FCF acumulado">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="cumFcf" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={C.accent} stopOpacity={0.18} />
              <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
          <XAxis dataKey="year" tick={AXIS} stroke={C.slate} />
          <YAxis tickFormatter={fmtK} tick={AXIS} stroke={C.slate} width={56} />
          <Tooltip formatter={(v: number) => eur(Number(v))} contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={0} stroke="#cbd5e1" />
          <Bar dataKey="cfo" name="CFO" fill={C.accent} radius={[3, 3, 0, 0]} maxBarSize={22} animationDuration={700} />
          <Bar dataKey="cfi" name="CFI" fill={C.slate} radius={[3, 3, 0, 0]} maxBarSize={22} animationDuration={700} />
          <Bar dataKey="cff" name="CFF" fill="#cbd5e1" radius={[3, 3, 0, 0]} maxBarSize={22} animationDuration={700} />
          <Area type="monotone" dataKey="cum" name="FCF acumulado" stroke={C.accent} strokeWidth={2} fill="url(#cumFcf)" dot={false} animationDuration={900} />
          <Line type="monotone" dataKey="fcf" name="FCF anual" stroke={C.ink} strokeWidth={2} dot={false} animationDuration={900} />
        </ComposedChart>
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
      <Panel title="Cashflows por año" subtitle="FV vs BESS">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={cashflows} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
            <XAxis dataKey="year" tick={AXIS} stroke={C.slate} />
            <YAxis tickFormatter={fmtK} tick={AXIS} stroke={C.slate} width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="fv" name="FV" fill={C.accent} radius={[3, 3, 0, 0]} maxBarSize={22} animationDuration={700} />
            <Bar dataKey="bess" name="BESS" fill={C.accentSoft} radius={[3, 3, 0, 0]} maxBarSize={22} animationDuration={700} />
          </ComposedChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Curvas de mercado" subtitle="Spread capture · Ancillary" delay={60}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curves} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
            <XAxis dataKey="year" tick={AXIS} stroke={C.slate} />
            <YAxis tick={AXIS} stroke={C.slate} width={48} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="spread" name="Spread capture" stroke={C.accent} dot={false} strokeWidth={2} animationDuration={900} />
            <Line type="monotone" dataKey="ancillary" name="Ancillary" stroke={C.amber} dot={false} strokeWidth={2} animationDuration={900} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Bridge VAN" subtitle="FV → BESS → Híbrido" delay={120}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={bridge} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
            <XAxis dataKey="name" tick={AXIS} stroke={C.slate} />
            <YAxis tickFormatter={fmtK} tick={AXIS} stroke={C.slate} width={48} />
            <Tooltip formatter={(v: number) => fmtK(v)} contentStyle={tooltipStyle} />
            <ReferenceLine y={0} stroke="#cbd5e1" />
            <Bar dataKey="value" name="VAN" radius={[3, 3, 0, 0]} maxBarSize={48} animationDuration={700}>
              {bridge.map((b) => (
                <Cell key={b.name} fill={b.value >= 0 ? C.pos : C.neg} />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Perfil DSCR" subtitle="Deuda subordinada" delay={180}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={dscr} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
            <XAxis dataKey="year" tick={AXIS} stroke={C.slate} />
            <YAxis tick={AXIS} stroke={C.slate} width={48} domain={[0, "auto"]} />
            <Tooltip formatter={(v: number) => `${Number(v).toFixed(2)}×`} contentStyle={tooltipStyle} />
            <ReferenceLine y={1} stroke={C.neg} strokeDasharray="4 4" />
            <Line type="monotone" dataKey="dscr" name="DSCR" stroke={C.accent} dot={false} strokeWidth={2} animationDuration={900} />
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
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {data.income_statement && <IncomeStatementChart is={data.income_statement} />}
      {data.cash_flow && <CashFlowChart cf={data.cash_flow} />}
    </div>
  );
}
