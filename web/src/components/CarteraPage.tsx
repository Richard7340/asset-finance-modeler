import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { listAssets, setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import PortfolioOverview from "./PortfolioOverview";
import AssetsMap from "./AssetsMap";
import { PortfolioAlerts } from "./Alerts";

type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
};

/**
 * Cartera — the operational command center. The day-to-day, richest view:
 * a geographic map of the operational assets, deviation/DSCR alerts, then the
 * full operational portfolio overview (KPIs + donut + bars + table). Each row
 * can be demoted back to an opportunity ("Devolver a oportunidad").
 */
export default function CarteraPage({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();

  // Cheap count for the header chip (the heavy aggregate lives inside
  // PortfolioOverview).
  const countQuery = useQuery({
    queryKey: ["assets", "operational"],
    queryFn: () => listAssets("operational"),
  });
  const count = countQuery.data?.length ?? 0;

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  // Demote an operational asset back to the opportunities bucket.
  const demote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "opportunity" });
    refresh();
  };

  const empty = !countQuery.isLoading && count === 0;

  return (
    <section className="mx-auto max-w-[1400px] space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-200 pb-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-600/10 text-accent-700">
          <Building2 size={18} strokeWidth={2} />
        </span>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-slate-900">
            Cartera · activos en operación
          </h2>
          <p className="text-xs text-slate-500">
            Gestión y seguimiento del día a día
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold tabular-nums text-slate-700">
          {count}
        </span>
      </div>

      {empty ? (
        <div className="grid h-64 place-items-center px-6 text-center text-sm text-slate-400">
          Aún no hay activos en operación. Promociona una oportunidad desde la
          pestaña Oportunidades para empezar a hacerle seguimiento.
        </div>
      ) : (
        <>
          {/* Operational map + deviation/DSCR alerts up top — the at-a-glance
              monitoring layer for the command center. */}
          <AssetsMap onOpenAsset={onOpenAsset} lifecycle="operational" />
          <PortfolioAlerts />
          <PortfolioOverview
            onOpenAsset={onOpenAsset}
            lifecycle="operational"
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
        </>
      )}
    </section>
  );
}
