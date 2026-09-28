import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { listAssets, setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import PortfolioOverview from "./PortfolioOverview";
import PortfolioHeader from "./PortfolioHeader";
import AssetsMap from "./AssetsMap";
import { PortfolioAlerts } from "./Alerts";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
  onVerOportunidades?: () => void;
};

/**
 * Cartera — the operational command center. Reads top-down like a fund
 * asset-management cockpit: headline NAV + aggregate KPIs, a slim operational
 * alerts strip, the analytics panels (composition + VAN + revenue), the dense
 * per-asset table, and finally the geographic map of the operational fleet.
 * Each row can be demoted back to an opportunity ("Devolver a oportunidad").
 */
export default function CarteraPage({ onOpenAsset, onVerOportunidades }: Props) {
  // Con la Cartera vacía, decir que lo guardado está en Oportunidades y cómo
  // pasarlo (29-sep: se veía todo a 0 y parecía que no había nada).
  const oportunidades = useQuery({ queryKey: ["assets", "opportunity"], queryFn: () => listAssets("opportunity") });
  const nOpo = oportunidades.data?.length ?? 0;
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
        vacio={
          nOpo > 0 ? (
            <div className="flex flex-col items-center gap-3">
              <div className="text-slate-600">
                Aún no hay activos en operación. Tienes <b>{nOpo}</b> {nOpo === 1 ? "activo" : "activos"} en Oportunidades.
              </div>
              <div className="max-w-md text-xs text-slate-400">
                Si ya está funcionando, pásalo a la cartera con «Marcar en operación», o díselo a tu agente. Al anotar sus datos reales pasa solo.
              </div>
              {onVerOportunidades && (
                <button type="button" onClick={onVerOportunidades} className="rounded-md bg-accent-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-700">
                  Ver oportunidades
                </button>
              )}
            </div>
          ) : undefined
        }
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
