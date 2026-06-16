import type React from "react";
import { eur, pct } from "../format";
import type { HeaderAggregate } from "./PortfolioOverview";

type Props = {
  /** Lucide icon element (already sized). */
  icon: React.ReactNode;
  /** Eyebrow / kicker over the title (e.g. "Activos en operación"). */
  eyebrow: string;
  /** Main page title (kept exact for tests on the page components). */
  title: string;
  /** One-line context subtitle. */
  subtitle: string;
  /** Live aggregate from PortfolioOverview. */
  agg: HeaderAggregate;
  /** Label for the headline metric (e.g. "NAV total" / "Valor estimado"). */
  navLabel: string;
};

/**
 * Premium page header band for the two portfolio pages. A clear title block on
 * the left, the headline aggregate (NAV total + nº activos, + TIR media when
 * present) prominent on the right. Sober indigo accent, lucide icon, no emojis;
 * theme-aware via the shared surface / slate utilities.
 */
export default function PortfolioHeader({
  icon,
  eyebrow,
  title,
  subtitle,
  agg,
  navLabel,
}: Props) {
  const dash = agg.loading ? "—" : undefined;
  return (
    <div className="surface overflow-hidden">
      {/* Thin accent rule along the top edge — the signature touch. */}
      <div className="h-0.5 w-full bg-gradient-to-r from-accent-600 via-accent-500 to-transparent" />
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-600/10 text-accent-700">
            {icon}
          </span>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-600 dark:text-accent-400">
              {eyebrow}
            </div>
            <h2 className="mt-0.5 text-xl font-semibold tracking-tight text-slate-900">
              {title}
            </h2>
            <p className="mt-1 max-w-xl text-sm text-slate-500">{subtitle}</p>
          </div>
        </div>

        {/* Headline aggregate band. */}
        <div className="flex shrink-0 items-stretch divide-x divide-slate-200 rounded-xl border border-slate-200 bg-slate-50/60 dark:divide-slate-700 dark:border-slate-700">
          <div className="px-4 py-2.5">
            <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
              {navLabel}
            </div>
            <div className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
              {dash ?? eur(agg.navTotal)}
            </div>
          </div>
          <div className="px-4 py-2.5">
            <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Nº activos
            </div>
            <div className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
              {dash ?? agg.count}
            </div>
          </div>
          {agg.irrWeighted !== undefined && (
            <div className="px-4 py-2.5">
              <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                TIR media
              </div>
              <div className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
                {dash ?? pct(agg.irrWeighted)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
