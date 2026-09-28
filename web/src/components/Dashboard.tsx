import type { SavedAssetSummary } from "../api";
import CarteraPage from "./CarteraPage";
import OportunidadesPage from "./OportunidadesPage";

/** The two primary landing pages. */
export type DashboardPage = "cartera" | "oportunidades";

type Props = {
  /** Which primary page to render. */
  page: DashboardPage;
  onOpenAsset: (a: SavedAssetSummary) => void;
  /** Cambiar de página (la Cartera vacía lleva a Oportunidades). */
  onIrA?: (p: DashboardPage) => void;
};

/**
 * Page switch for the two primary landing pages. The header drives `page`;
 * Cartera (operational) is the default. Each page owns its own lifecycle bucket
 * and its own promote/demote action, so an asset can move both ways and both
 * pages stay in sync via the broad ["assets"]/["portfolio"] invalidations.
 */
export default function Dashboard({ page, onOpenAsset, onIrA }: Props) {
  return page === "oportunidades" ? (
    <OportunidadesPage onOpenAsset={onOpenAsset} />
  ) : (
    <CarteraPage onOpenAsset={onOpenAsset} onVerOportunidades={() => onIrA?.("oportunidades")} />
  );
}
