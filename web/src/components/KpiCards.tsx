import type { RunResult } from "../api";
import { isHybridResult } from "../api";
import { eur, mult, pct } from "../format";

type Tone = "good" | "thin" | "bad" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  good: "text-emerald-600",
  thin: "text-amber-600",
  bad: "text-rose-600",
  neutral: "text-slate-800",
};

function Card({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`mt-1 text-2xl font-semibold tabular-nums ${TONE_CLASS[tone]}`}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
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
      <Card label="VAN Híbrido" value={eur(k.npv_hybrid)} tone={npvTone(k.npv_hybrid)} />
      <Card label="VAN FV" value={eur(k.npv_fv)} tone={npvTone(k.npv_fv)} />
      <Card label="VAN BESS" value={eur(k.npv_bess)} tone={npvTone(k.npv_bess)} />
      <Card
        label="MOIC sub"
        value={mult(k.moic_sub)}
        tone={k.moic_sub >= 1.3 ? "good" : k.moic_sub >= 1 ? "thin" : "bad"}
      />
      <Card label="DSCR sub medio" value={mult(k.dscr_sub_avg)} tone={dscrTone(k.dscr_sub_avg)} />
      <Card label="DSCR sub mín" value={mult(k.dscr_sub_min)} tone={dscrTone(k.dscr_sub_min)} />
      <Card label="DSCR senior mín" value={mult(k.dscr_senior_min)} tone={dscrTone(k.dscr_senior_min)} />
      <Card label="Recovery" value={mult(k.recovery)} tone={k.recovery >= 1 ? "good" : "thin"} />
    </>
  );
}

/** Generic infra/business KPI set. */
function GenericCards({ k }: { k: Record<string, number> }) {
  const hasDscr = Number.isFinite(k.dscr_min) && k.dscr_min > 0;
  return (
    <>
      <Card label="VAN" value={eur(k.npv)} tone={npvTone(k.npv)} />
      <Card label="TIR proyecto" value={pct(k.irr_project)} tone={irrTone(k.irr_project)} />
      <Card label="TIR equity" value={pct(k.irr_equity)} tone={irrTone(k.irr_equity)} />
      {hasDscr && (
        <Card label="DSCR mín" value={mult(k.dscr_min)} tone={dscrTone(k.dscr_min)} />
      )}
      <Card label="CAPEX total" value={eur(k.total_capex)} tone="neutral" />
    </>
  );
}

export default function KpiCards({ data }: { data: RunResult }) {
  const k = data.kpis ?? {};
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {isHybridResult(data) ? <HybridCards k={k} /> : <GenericCards k={k} />}
    </div>
  );
}
