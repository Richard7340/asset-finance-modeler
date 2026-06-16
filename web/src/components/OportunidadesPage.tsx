import { useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import PortfolioOverview from "./PortfolioOverview";
import PortfolioHeader from "./PortfolioHeader";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

/**
 * Oportunidades — valuation pipeline. Simulations evaluated for purchase or
 * investment; these do NOT count as portfolio. Reads top-down: headline
 * estimated value + aggregate KPIs, the comparative analytics panels
 * (composition + VAN + revenue), then the dense per-asset table. Each row can
 * be promoted into operation ("Marcar en operación"), moving it to Cartera.
 *
 * No map here by design: opportunities are a valuation funnel, not a monitored
 * portfolio, and many are still abstract (no fixed site). The geographic view
 * belongs on Cartera, where it answers an operational question. This keeps the
 * Oportunidades page focused on the comparative economics.
 */
export default function OportunidadesPage({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();

  // Promote an opportunity into operation; it moves to the Cartera page.
  const promote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "operational" });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  return (
    <section className="mx-auto max-w-[1400px]">
      <PortfolioOverview
        onOpenAsset={onOpenAsset}
        lifecycle="opportunity"
        header={(agg) => (
          <PortfolioHeader
            icon={<Search size={20} strokeWidth={2} />}
            eyebrow="Pipeline de valoraciones"
            title="Oportunidades · valoraciones"
            subtitle="Simulaciones para evaluar compra o inversión. No cuentan como cartera."
            navLabel="Valor estimado"
            agg={agg}
          />
        )}
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
    </section>
  );
}
