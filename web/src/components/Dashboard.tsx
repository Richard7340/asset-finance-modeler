import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Search } from "lucide-react";
import { listAssets, setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import AssetGroup from "./AssetGroup";
import PortfolioOverview from "./PortfolioOverview";
import AssetsMap from "./AssetsMap";
import { PortfolioAlerts } from "./Alerts";

type Props = {
  onOpenAsset: (a: SavedAssetSummary) => void;
};

export default function Dashboard({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();
  // Lightweight counts for the section headers (cheap list, not the heavy aggregate).
  const allQuery = useQuery({ queryKey: ["assets", "all"], queryFn: () => listAssets() });
  const all = allQuery.data ?? [];

  const counts = useMemo(() => {
    let op = 0;
    let opp = 0;
    for (const a of all) (a.lifecycle === "operational" ? (op += 1) : (opp += 1));
    return { op, opp };
  }, [all]);

  const promote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "operational" });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  return (
    <div className="mx-auto max-w-[1400px] space-y-10">
      <AssetGroup
        title="Cartera · activos en operación"
        subtitle="Gestión y seguimiento del día a día"
        icon={<Building2 size={18} strokeWidth={2} />}
        count={counts.op}
      >
        <PortfolioAlerts />
        <PortfolioOverview onOpenAsset={onOpenAsset} lifecycle="operational" />
        <AssetsMap onOpenAsset={onOpenAsset} />
      </AssetGroup>

      <AssetGroup
        title="Oportunidades · valoraciones"
        subtitle="Simulaciones para evaluar compra o inversión (no cuentan como cartera)"
        icon={<Search size={18} strokeWidth={2} />}
        count={counts.opp}
      >
        <PortfolioOverview
          onOpenAsset={onOpenAsset}
          lifecycle="opportunity"
          rowAction={(a) => (
            <button
              type="button"
              onClick={() => promote(a)}
              className="rounded-md border border-accent-300 bg-accent-50 px-2.5 py-1 text-xs font-medium text-accent-700 transition hover:bg-accent-100"
            >
              Marcar en operación
            </button>
          )}
        />
      </AssetGroup>
    </div>
  );
}
