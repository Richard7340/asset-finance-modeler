import type React from "react";
import { MapPin, TrendingUp, TrendingDown, ArrowUpRight } from "lucide-react";
import type { PortfolioAsset, SavedAssetSummary, Lifecycle } from "../api";
import { eur, pct } from "../format";
import Sparkline from "./Sparkline";
import { assetTech } from "../lib/assetTech";

const POS = "#10b981"; // emerald-500
const NEG = "#f43f5e"; // rose-500
const ACCENT = "#6366f1"; // indigo-500

export type AssetCardRow = {
  id: string;
  name: string;
  model_id: string;
  location?: string | null;
};

type Props = {
  rows: AssetCardRow[];
  metricsById: Map<string, PortfolioAsset>;
  seriesById: Map<string, number[]>;
  excluded: Set<string>;
  totalNpv: number;
  /** Lifecycle scope drives the status chip + which figures lead. */
  lifecycle?: Lifecycle;
  onToggle: (id: string) => void;
  onOpen: (id: string) => void;
  /** Optional promote/demote control rendered inside the card footer. */
  rowAction?: (a: SavedAssetSummary) => React.ReactNode;
  /** Resolve the full saved-asset summary for the row action. */
  resolveAsset: (id: string) => SavedAssetSummary | undefined;
};

/** Status chip: en operación / oportunidad (sober, theme-shared). */
function StatusChip({ lifecycle }: { lifecycle?: Lifecycle }) {
  const isOp = lifecycle === "operational";
  const label = isOp ? "En operación" : "Oportunidad";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
        isOp
          ? "bg-accent-50 text-accent-700"
          : "bg-slate-100 text-slate-500"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${isOp ? "bg-accent-500" : "bg-slate-400"}`}
        aria-hidden
      />
      {label}
    </span>
  );
}

/** A single headline figure inside the card (label over a tabular-nums value). */
function Figure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "mute";
}) {
  const cls =
    tone === "pos"
      ? "text-emerald-600"
      : tone === "neg"
        ? "text-rose-600"
        : tone === "mute"
          ? "text-slate-400"
          : "text-slate-900";
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className={`mt-0.5 text-sm font-semibold tabular-nums ${cls}`}>{value}</div>
    </div>
  );
}

/**
 * The hero of the Cartera / Oportunidades pages: a responsive grid of rich,
 * clickable asset cards. Each card leads with the asset and surfaces the
 * headline economics, a sober status chip, a mini trend curve (sourced from the
 * asset's stored result series), the include-in-aggregate toggle and the
 * promote/demote action. This is the at-a-glance "total control" view.
 */
export default function AssetCards({
  rows,
  metricsById,
  seriesById,
  excluded,
  totalNpv,
  lifecycle,
  onToggle,
  onOpen,
  rowAction,
  resolveAsset,
}: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {rows.map((r) => {
        const m = metricsById.get(r.id);
        const isIncluded = !excluded.has(r.id);
        const tech = assetTech(r.model_id);
        const TechIcon = tech.Icon;
        const series = seriesById.get(r.id) ?? [];
        const npv = m?.npv;
        const irr = m?.irr;
        const contrib = m && totalNpv !== 0 && isIncluded ? m.npv / totalNpv : undefined;
        const npvPositive = (npv ?? 0) >= 0;
        const sparkColor = !isIncluded ? "#94a3b8" : npvPositive ? POS : NEG;
        const TrendIcon = npvPositive ? TrendingUp : TrendingDown;

        return (
          <div
            key={r.id}
            role="button"
            tabIndex={0}
            onClick={() => onOpen(r.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen(r.id);
              }
            }}
            className={`surface surface-hover group relative flex cursor-pointer flex-col overflow-hidden p-4 transition hover:-translate-y-0.5 ${
              isIncluded ? "" : "opacity-60"
            }`}
          >
            {/* Accent rule, tone cue for the asset's value sign. */}
            <span
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{ backgroundColor: !isIncluded ? "#cbd5e1" : npvPositive ? POS : NEG }}
              aria-hidden
            />

            {/* Header: tech icon + name + status chip + drill-in cue. */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-start gap-2.5">
                <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-50 text-accent-600">
                  <TechIcon size={16} strokeWidth={2} />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900 transition group-hover:text-accent-700">
                    {r.name}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-400">
                    <span className="truncate">{tech.label}</span>
                    {r.location && (
                      <>
                        <span aria-hidden>·</span>
                        <span className="inline-flex items-center gap-0.5 truncate">
                          <MapPin size={11} strokeWidth={2} />
                          {r.location}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <ArrowUpRight
                size={15}
                strokeWidth={2}
                className="shrink-0 text-slate-300 transition group-hover:text-accent-500"
                aria-hidden
              />
            </div>

            {/* Headline figures. */}
            <div className="mt-3.5 grid grid-cols-3 gap-3">
              <Figure
                label="VAN"
                value={npv !== undefined ? eur(npv) : "—"}
                tone={npv === undefined ? "mute" : npvPositive ? "pos" : "neg"}
              />
              <Figure
                label="TIR"
                value={irr !== undefined && Number.isFinite(irr) ? pct(irr) : "—"}
                tone={
                  irr === undefined || !Number.isFinite(irr)
                    ? "mute"
                    : irr < 0
                      ? "neg"
                      : undefined
                }
              />
              <Figure
                label={lifecycle === "opportunity" ? "Rentab." : "% cartera"}
                value={
                  lifecycle === "opportunity"
                    ? m && Number.isFinite(m.yield_pct)
                      ? pct(m.yield_pct)
                      : "—"
                    : contrib !== undefined
                      ? pct(contrib)
                      : "—"
                }
                tone={contrib === undefined && lifecycle !== "opportunity" ? "mute" : undefined}
              />
            </div>

            {/* Mini trend curve + secondary figures (CAPEX / ingresos). */}
            <div className="mt-3 flex items-end justify-between gap-3">
              <div className="flex gap-4 text-[11px] text-slate-400">
                <span>
                  CAPEX{" "}
                  <span className="tabular-nums text-slate-600">
                    {m ? eur(m.capex) : "—"}
                  </span>
                </span>
                <span>
                  Ingresos{" "}
                  <span className="tabular-nums text-slate-600">
                    {m ? eur(m.revenue_y1) : "—"}
                  </span>
                </span>
              </div>
              {series.length >= 2 ? (
                <Sparkline
                  values={series}
                  color={sparkColor}
                  width={96}
                  height={28}
                  className="shrink-0"
                />
              ) : (
                <TrendIcon
                  size={18}
                  strokeWidth={2}
                  className="shrink-0 text-slate-300"
                  aria-hidden
                />
              )}
            </div>

            {/* Footer: include toggle + status + row action. */}
            <div className="mt-3.5 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
              <label
                className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-500"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={isIncluded}
                  onChange={() => onToggle(r.id)}
                  aria-label={`Incluir ${r.name} en el agregado`}
                  className="h-3.5 w-3.5 cursor-pointer accent-accent-600"
                />
                Incluir
              </label>
              <div className="flex items-center gap-2">
                <StatusChip lifecycle={lifecycle} />
                {rowAction && (
                  <span onClick={(e) => e.stopPropagation()}>
                    {(() => {
                      const a = resolveAsset(r.id);
                      return a ? rowAction(a) : null;
                    })()}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export { ACCENT };
