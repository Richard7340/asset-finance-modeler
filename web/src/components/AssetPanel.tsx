import { useQuery } from "@tanstack/react-query";
import { listModels, listAssets } from "../api";
import type { AssetType, ModelSummary, SavedAssetSummary } from "../api";
import { eur, fmtDate, pct } from "../format";

type Props = {
  selectedModelId: string | null;
  selectedAssetId: string | null;
  onSelectModel: (m: ModelSummary) => void;
  onSelectAsset: (a: SavedAssetSummary) => void;
  onDeleteAsset: (id: string) => void;
};

// Spanish grouping of asset types into business families.
const GROUPS: { title: string; types: AssetType[] }[] = [
  { title: "Energía / Renovables", types: ["solar", "bess", "wind", "datacenter"] },
  { title: "Híbrido", types: ["hybrid", "svj"] },
  { title: "Negocio", types: ["business"] },
  { title: "Inmobiliario", types: ["real_estate"] },
];

/** Pick one headline KPI for a saved asset card. */
function headlineKpi(kpis: Record<string, number>): string {
  if (kpis.npv_hybrid !== undefined) return `VAN ${eur(kpis.npv_hybrid)}`;
  if (kpis.npv !== undefined) return `VAN ${eur(kpis.npv)}`;
  if (kpis.irr_equity !== undefined) return `TIR eq. ${pct(kpis.irr_equity)}`;
  return "";
}

export default function AssetPanel({
  selectedModelId,
  selectedAssetId,
  onSelectModel,
  onSelectAsset,
  onDeleteAsset,
}: Props) {
  const modelsQuery = useQuery({ queryKey: ["models"], queryFn: listModels });
  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: listAssets });

  const models = modelsQuery.data ?? [];
  const assets = assetsQuery.data ?? [];

  return (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto">
      {/* Mi cartera */}
      <section>
        <h2 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Mi cartera
        </h2>
        {assetsQuery.isLoading ? (
          <p className="px-1 text-xs text-slate-400">Cargando…</p>
        ) : assets.length === 0 ? (
          <p className="px-1 text-xs text-slate-400">
            Sin simulaciones guardadas todavía.
          </p>
        ) : (
          <ul className="space-y-1">
            {assets.map((a) => {
              const active = a.id === selectedAssetId;
              return (
                <li key={a.id}>
                  <div
                    className={`group flex items-start justify-between gap-2 rounded-md border px-2.5 py-2 text-left transition ${
                      active
                        ? "border-accent-500 bg-accent-50"
                        : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectAsset(a)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <div className="truncate text-sm font-medium text-slate-800">
                        {a.name}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-[11px] text-slate-500">
                        <span>{fmtDate(a.created_at)}</span>
                        {headlineKpi(a.kpis) && (
                          <span className="font-medium text-slate-600">
                            {headlineKpi(a.kpis)}
                          </span>
                        )}
                      </div>
                    </button>
                    <button
                      type="button"
                      title="Eliminar"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`¿Eliminar "${a.name}"?`)) onDeleteAsset(a.id);
                      }}
                      className="mt-0.5 shrink-0 rounded px-1.5 text-xs uppercase tracking-wide text-slate-300 hover:bg-rose-50 hover:text-rose-500"
                    >
                      Eliminar
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Modelos */}
      <section>
        <h2 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Modelos
        </h2>
        {modelsQuery.isLoading ? (
          <p className="px-1 text-xs text-slate-400">Cargando…</p>
        ) : (
          <div className="space-y-4">
            {GROUPS.map((group) => {
              const groupModels = models.filter((m) =>
                group.types.includes(m.asset_type),
              );
              if (groupModels.length === 0) return null;
              return (
                <div key={group.title}>
                  <div className="mb-1 px-1 text-[11px] font-medium text-slate-500">
                    {group.title}
                  </div>
                  <ul className="space-y-1">
                    {groupModels.map((m) => {
                      const active =
                        m.id === selectedModelId && selectedAssetId === null;
                      return (
                        <li key={m.id}>
                          <button
                            type="button"
                            onClick={() => onSelectModel(m)}
                            className={`w-full truncate rounded-md border px-2.5 py-1.5 text-left text-sm transition ${
                              active
                                ? "border-accent-500 bg-accent-50 text-slate-900"
                                : "border-transparent text-slate-700 hover:border-slate-200 hover:bg-slate-50"
                            }`}
                          >
                            {m.name}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </nav>
  );
}
