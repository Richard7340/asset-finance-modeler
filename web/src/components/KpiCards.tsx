import type { RunResult } from "../api";
import { eur, mult } from "../format";

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
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${TONE_CLASS[tone]}`}>
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
  if (v >= 1.3) return "good";
  if (v >= 1.0) return "thin";
  return "bad";
}

export default function KpiCards({ data }: { data: RunResult }) {
  const k = data.kpis;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <Card label="NPV Híbrido" value={eur(k.npv_hybrid)} tone={npvTone(k.npv_hybrid)} />
      <Card label="NPV FV" value={eur(k.npv_fv)} tone={npvTone(k.npv_fv)} />
      <Card label="NPV BESS" value={eur(k.npv_bess)} tone={npvTone(k.npv_bess)} />
      <Card
        label="MOIC sub"
        value={mult(k.moic_sub)}
        tone={k.moic_sub >= 1.3 ? "good" : k.moic_sub >= 1 ? "thin" : "bad"}
      />
      <Card label="DSCR sub avg" value={mult(k.dscr_sub_avg)} tone={dscrTone(k.dscr_sub_avg)} />
      <Card label="DSCR sub min" value={mult(k.dscr_sub_min)} tone={dscrTone(k.dscr_sub_min)} />
      <Card
        label="DSCR senior min"
        value={mult(k.dscr_senior_min)}
        tone={dscrTone(k.dscr_senior_min)}
      />
      <Card
        label="Recovery"
        value={mult(k.recovery)}
        tone={k.recovery >= 1 ? "good" : "thin"}
      />
    </div>
  );
}
