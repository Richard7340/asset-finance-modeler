import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { listAssets, setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import PortfolioOverview from "./PortfolioOverview";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

/**
 * Oportunidades — valuation pipeline. Simulations evaluated for purchase or
 * investment; these do NOT count as portfolio. Its own valuation dashboard
 * (VAN/TIR/MOIC KPIs + donut + bars + table). Each row can be promoted into
 * operation ("Marcar en operación"), which moves it to the Cartera page.
 *
 * No map here by design: opportunities are a valuation funnel, not a monitored
 * portfolio, and many are still abstract (no fixed site). The geographic view
 * belongs on Cartera, where it answers an operational question. This keeps the
 * Oportunidades page focused on the comparative economics.
 */
export default function OportunidadesPage({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();

  const countQuery = useQuery({
    queryKey: ["assets", "opportunity"],
    queryFn: () => listAssets("opportunity"),
  });
  const count = countQuery.data?.length ?? 0;

  // Promote an opportunity into operation; it moves to the Cartera page.
  const promote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "operational" });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  const empty = !countQuery.isLoading && count === 0;

  return (
    <section className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-200 pb-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-600/10 text-accent-700">
          <Search size={18} strokeWidth={2} />
        </span>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-slate-900">
            Oportunidades · valoraciones
          </h2>
          <p className="text-xs text-slate-500">
            Simulaciones para evaluar compra o inversión (no cuentan como
            cartera)
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold tabular-nums text-slate-700">
          {count}
        </span>
      </div>

      {empty ? (
        <div className="grid h-64 place-items-center px-6 text-center text-sm text-slate-400">
          Aún no hay oportunidades. Crea y guarda un activo desde un modelo para
          evaluarlo aquí.
        </div>
      ) : (
        <PortfolioOverview
          onOpenAsset={onOpenAsset}
          lifecycle="opportunity"
          rowAction={(a) => (
            <button
              type="button"
              onClick={() => promote(a)}
              className="rounded-md border border-accent-300 bg-accent-50 px-2.5 py-1 text-xs font-medium text-accent-700 transition hover:bg-accent-100"
              title="Promocionar esta oportunidad a un activo en operación"
            >
              Marcar en operación
            </button>
          )}
        />
      )}
    </section>
  );
}
