import { useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import PortfolioOverview from "./PortfolioOverview";
import PortfolioHeader from "./PortfolioHeader";
import AssetsMap from "./AssetsMap";
import { PortfolioAlerts } from "./Alerts";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

/**
 * Cartera — the operational command center. Reads top-down like a fund
 * asset-management cockpit: headline NAV + aggregate KPIs, a slim operational
 * alerts strip, the analytics panels (composition + VAN + revenue), the dense
 * per-asset table, and finally the geographic map of the operational fleet.
 * Each row can be demoted back to an opportunity ("Devolver a oportunidad").
 */
export default function CarteraPage({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  // Demote an operational asset back to the opportunities bucket.
  const demote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "opportunity" });
    refresh();
  };

  return (
    <section className="mx-auto max-w-[1400px]">
      <PortfolioOverview
        onOpenAsset={onOpenAsset}
        lifecycle="operational"
        header={(agg) => (
          <PortfolioHeader
            icon={<Building2 size={20} strokeWidth={2} />}
            eyebrow="Activos en operación"
            title="Cartera · activos en operación"
            subtitle="Gestión y seguimiento del día a día de la cartera en explotación."
            navLabel="NAV total"
            agg={agg}
          />
        )}
        alertsSlot={<PortfolioAlerts />}
        mapSlot={<AssetsMap onOpenAsset={onOpenAsset} lifecycle="operational" />}
        rowAction={(a) => (
          <button
            type="button"
            onClick={() => demote(a)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
            title="Devolver este activo a la lista de oportunidades"
          >
            Devolver a oportunidad
          </button>
        )}
      />
    </section>
  );
}
