import type { RunResult } from "../api";
import { isHybridResult } from "../api";
import { eur, mult, pct } from "../format";
import AnimatedNumber from "./AnimatedNumber";
import Sparkline from "./Sparkline";
import { useStaggerReveal } from "./Reveal";

type Tone = "good" | "thin" | "bad" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  good: "text-emerald-600",
  thin: "text-amber-600",
  bad: "text-rose-600",
  neutral: "text-slate-900",
};

const TONE_RAIL: Record<Tone, string> = {
  good: "bg-emerald-500/70",
  thin: "bg-amber-500/70",
  bad: "bg-rose-500/70",
  neutral: "bg-accent-500/60",
};

// Sparkline stroke per tone (kept sober; neutral uses the indigo accent).
const TONE_SPARK: Record<Tone, string> = {
  good: "#10b981",
  thin: "#f59e0b",
  bad: "#f43f5e",
  neutral: "#6366f1",
};

function Card({
  label,
  value,
  format,
  tone = "neutral",
  hint,
  series,
}: {
  label: string;
  value: number;
  format: (n: number) => string;
  tone?: Tone;
  hint?: string;
  /** Optional mini-trend rendered to the right of the figure. */
  series?: number[];
}) {
  const hasSpark = Array.isArray(series) && series.filter(Number.isFinite).length >= 2;
  return (
    <div className="surface surface-hover relative overflow-hidden p-4">
      <span
        className={`absolute inset-y-3 left-0 w-0.5 rounded-full ${TONE_RAIL[tone]}`}
        aria-hidden
      />
      <div className="pl-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </div>
        <div className="mt-1.5 flex items-end justify-between gap-2">
          <AnimatedNumber
            value={value}
            format={format}
            className={`block text-2xl font-semibold tabular-nums ${TONE_CLASS[tone]}`}
          />
          {hasSpark && (
            <Sparkline
              values={series as number[]}
              color={TONE_SPARK[tone]}
              className="shrink-0 opacity-90"
            />
          )}
        </div>
        {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
      </div>
    </div>
  );
}

function npvTone(v: number): Tone {
  if (v > 0) return "good";
  if (v > -500_000) return "thin";
  return "bad";
}

function dscrTone(v: number): Tone {
  if (!Number.isFinite(v) || v <= 0) return "neutral";
  if (v >= 1.3) return "good";
  if (v >= 1.0) return "thin";
  return "bad";
}

function irrTone(v: number): Tone {
  if (v >= 0.1) return "good";
  if (v >= 0.05) return "thin";
  return "bad";
}

/** Hybrid (svj) KPI set. */
function HybridCards({ k }: { k: Record<string, number> }) {
  return (
    <>
      <Card label="VAN Híbrido" value={k.npv_hybrid} format={eur} tone={npvTone(k.npv_hybrid)} />
      <Card label="VAN FV" value={k.npv_fv} format={eur} tone={npvTone(k.npv_fv)} />
      <Card label="VAN BESS" value={k.npv_bess} format={eur} tone={npvTone(k.npv_bess)} />
      <Card
        label="MOIC sub"
        value={k.moic_sub}
        format={mult}
        tone={k.moic_sub >= 1.3 ? "good" : k.moic_sub >= 1 ? "thin" : "bad"}
      />
      <Card label="DSCR sub medio" value={k.dscr_sub_avg} format={mult} tone={dscrTone(k.dscr_sub_avg)} />
      <Card label="DSCR sub mín" value={k.dscr_sub_min} format={mult} tone={dscrTone(k.dscr_sub_min)} />
      <Card label="DSCR senior mín" value={k.dscr_senior_min} format={mult} tone={dscrTone(k.dscr_senior_min)} />
      <Card label="Recovery" value={k.recovery} format={mult} tone={k.recovery >= 1 ? "good" : "thin"} />
    </>
  );
}

/** Cumulative FCF series from a cash flow (CFO + CFI), for the VAN tile trend. */
function cumulativeFcf(data: RunResult): number[] | undefined {
  const cf = data.cash_flow;
  if (!cf || !cf.years?.length) return undefined;
  let cum = 0;
  return cf.years.map((_, i) => {
    cum += (cf.cfo[i] ?? 0) + (cf.cfi[i] ?? 0);
    return cum;
  });
}

/** Generic infra/business KPI set. */
function GenericCards({ data }: { data: RunResult }) {
  const k = data.kpis ?? {};
  const hasDscr = Number.isFinite(k.dscr_min) && k.dscr_min > 0;
  const ebitda = data.income_statement?.rows?.ebitda;
  return (
    <>
      {/* VAN carries the cumulative-FCF trend; EBITDA carries its own series. */}
      <Card label="VAN" value={k.npv} format={eur} tone={npvTone(k.npv)} series={cumulativeFcf(data)} />
      <Card label="TIR proyecto" value={k.irr_project} format={pct} tone={irrTone(k.irr_project)} series={ebitda} />
      <Card label="TIR equity" value={k.irr_equity} format={pct} tone={irrTone(k.irr_equity)} />
      {hasDscr && (
        <Card label="DSCR mín" value={k.dscr_min} format={mult} tone={dscrTone(k.dscr_min)} />
      )}
      <Card label="CAPEX total" value={k.total_capex} format={eur} tone="neutral" />
    </>
  );
}

export default function KpiCards({ data }: { data: RunResult }) {
  const k = data.kpis ?? {};
  const hybrid = isHybridResult(data);
  // Re-stagger when the model / shape changes.
  const ref = useStaggerReveal<HTMLDivElement>([hybrid, Object.keys(k).length]);
  return (
    <div
      ref={ref}
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
    >
      {hybrid ? <HybridCards k={k} /> : <GenericCards data={data} />}
    </div>
  );
}
