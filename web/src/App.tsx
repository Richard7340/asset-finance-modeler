import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAsset,
  getAsset,
  getSchema,
  isHybridResult,
  isEmbed,
  setLifecycle,
} from "./api";
import type {
  Lifecycle,
  ModelSummary,
  OverrideValue,
  Overrides,
  SavedAssetSummary,
  TrackingFrequency,
} from "./api";
import { ArrowLeft, Building2, Moon, Search, Sun } from "lucide-react";
import { useRun } from "./hooks/useRun";
import { useTheme } from "./hooks/useTheme";
import { fmtDateTime } from "./format";
import AssetPanel from "./components/AssetPanel";
import Dashboard from "./components/Dashboard";
import type { DashboardPage } from "./components/Dashboard";
import DynamicInputs from "./components/DynamicInputs";
import CurvesPanel from "./components/CurvesPanel";
import KpiCards from "./components/KpiCards";
import IncomeStatementTable from "./components/IncomeStatement";
import CashFlowTable from "./components/CashFlowTable";
import Charts from "./components/Charts";
import Toolbar from "./components/Toolbar";
import ViewTransition from "./components/ViewTransition";
import ActualsGrid from "./components/ActualsGrid";
import VariancePanel from "./components/VariancePanel";
import LivePanel from "./components/LivePanel";
import { AssetAlerts } from "./components/Alerts";

type Selection = {
  modelId: string;
  modelName: string;
  // When set, the editor reflects a saved asset being reviewed.
  assetId: string | null;
  savedAt: string | null;
  // Lifecycle metadata carried from the dashboard/asset summary. The asset
  // detail endpoint does not return these, so we keep them from the selection
  // (every caller passes a SavedAssetSummary which carries them).
  lifecycle: Lifecycle | null;
  trackingFrequency: TrackingFrequency | null;
};

type View = "portfolio" | "detail";

export default function App() {
  const queryClient = useQueryClient();
  const { theme, toggle: toggleTheme } = useTheme();
  const [view, setView] = useState<View>("portfolio");
  // Which primary page is active. Cartera (operational) is the landing page.
  const [page, setPage] = useState<DashboardPage>("cartera");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({});

  const modelId = selection?.modelId ?? null;

  // Schema for the selected model.
  const schemaQuery = useQuery({
    queryKey: ["schema", modelId],
    queryFn: () => getSchema(modelId as string),
    enabled: !!modelId,
  });

  const { data: result, isFetching } = useRun(modelId, overrides, !!modelId);

  // --- selection handlers ---

  const selectModel = (m: ModelSummary) => {
    setSelection({
      modelId: m.id,
      modelName: m.name,
      assetId: null,
      savedAt: null,
      lifecycle: null,
      trackingFrequency: null,
    });
    setOverrides({}); // defaults come from schema; empty overrides => backend defaults
    setView("detail");
  };

  const selectAsset = async (a: SavedAssetSummary) => {
    const full = await getAsset(a.id);
    setSelection({
      modelId: full.model_id,
      modelName: full.name,
      assetId: full.id,
      savedAt: full.created_at,
      // The detail endpoint omits lifecycle; carry it from the summary.
      lifecycle: a.lifecycle ?? null,
      trackingFrequency: a.tracking_frequency ?? null,
    });
    setOverrides(full.overrides ?? {});
    // Remember which page this asset belongs to, so "back" returns there.
    if (a.lifecycle === "operational") setPage("cartera");
    else if (a.lifecycle === "opportunity") setPage("oportunidades");
    setView("detail");
  };

  // Switch to a primary page (from the header tabs or the detail back button).
  const goToPage = (p: DashboardPage) => {
    setPage(p);
    setView("portfolio");
  };

  const handleDeleteAsset = async (id: string) => {
    await deleteAsset(id);
    if (selection?.assetId === id) {
      setSelection(null);
      setOverrides({});
    }
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  const refreshCartera = () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  // Demote the asset currently open in the detail editor back to an
  // opportunity, then return to the Oportunidades page where it now lives.
  const demoteCurrent = async () => {
    if (!selection?.assetId) return;
    await setLifecycle(selection.assetId, { lifecycle: "opportunity" });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    goToPage("oportunidades");
  };

  // Editing an input clears the "reviewing saved asset" banner (it becomes a
  // live edit) but keeps the same model.
  const setOne = (path: string, value: number) => {
    setOverrides((prev) => ({ ...prev, [path]: value }));
    setSelection((prev) =>
      prev && prev.assetId ? { ...prev, assetId: null, savedAt: null } : prev,
    );
  };

  // Generic override setter: curve selection (string), custom points (number[])
  // or clearing a key (undefined). Also clears the "reviewing saved asset" flag.
  const setOverride = (path: string, value: OverrideValue | undefined) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (value === undefined) delete next[path];
      else next[path] = value;
      return next;
    });
    setSelection((prev) =>
      prev && prev.assetId ? { ...prev, assetId: null, savedAt: null } : prev,
    );
  };

  const recalcBadge = isFetching ? (
    <span className="flex items-center gap-1.5 text-xs text-slate-300">
      <span className="h-2 w-2 animate-pulse rounded-full bg-accent-400" />
      recalculando…
    </span>
  ) : null;

  const hybrid = result ? isHybridResult(result) : false;

  const center = useMemo(() => {
    if (!modelId) {
      return (
        <div className="grid h-full place-items-center text-sm text-slate-400">
          Selecciona un modelo o una simulación.
        </div>
      );
    }
    if (schemaQuery.isLoading) {
      return <div className="p-2 text-sm text-slate-400">Cargando parámetros…</div>;
    }
    if (schemaQuery.error || !schemaQuery.data) {
      return (
        <div className="p-2 text-sm text-rose-500">
          No se pudieron cargar los parámetros.
        </div>
      );
    }
    return (
      <DynamicInputs
        schema={schemaQuery.data}
        overrides={overrides}
        onChangeNumber={setOne}
        onChangeOverride={setOverride}
      />
    );
  }, [modelId, schemaQuery.isLoading, schemaQuery.error, schemaQuery.data, overrides]);

  return (
    <div className="flex h-full min-h-screen flex-col bg-slate-50 text-slate-900">
      {!isEmbed && (
        <header className="sticky top-0 z-20 border-b border-ink-700/60 bg-ink-900 text-slate-100 shadow-sm">
          <div className="flex items-center justify-between gap-3 px-6 py-3">
            <div className="flex items-center gap-3">
              <span
                className="grid h-8 w-8 place-items-center rounded-md bg-accent-600/90 text-sm font-bold tracking-tight text-white shadow-inner"
                aria-hidden
              >
                G
              </span>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">
                  Gestnova
                </div>
                <h1 className="text-base font-semibold text-white">
                  Plataforma de Valoración de Activos
                </h1>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <nav className="flex items-center gap-1 rounded-lg bg-white/5 p-1">
                <button
                  type="button"
                  onClick={() => goToPage("cartera")}
                  aria-current={
                    view === "portfolio" && page === "cartera" ? "page" : undefined
                  }
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    view === "portfolio" && page === "cartera"
                      ? "bg-white/15 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Building2 size={15} strokeWidth={2} />
                  Cartera
                </button>
                <button
                  type="button"
                  onClick={() => goToPage("oportunidades")}
                  aria-current={
                    view === "portfolio" && page === "oportunidades"
                      ? "page"
                      : undefined
                  }
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    view === "portfolio" && page === "oportunidades"
                      ? "bg-white/15 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Search size={15} strokeWidth={2} />
                  Oportunidades
                </button>
              </nav>
              {view === "detail" && (
                <button
                  type="button"
                  onClick={() => goToPage(page)}
                  className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-slate-300 transition hover:bg-white/5 hover:text-white"
                >
                  <ArrowLeft size={15} strokeWidth={2} />
                  {page === "oportunidades"
                    ? "Volver a Oportunidades"
                    : "Volver a Cartera"}
                </button>
              )}
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={theme === "dark" ? "Tema claro" : "Tema oscuro"}
                title={theme === "dark" ? "Tema claro" : "Tema oscuro"}
                className="grid h-8 w-8 place-items-center rounded-md text-slate-300 transition hover:bg-white/5 hover:text-white"
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              {recalcBadge}
              {view === "detail" && selection && (
                <Toolbar
                  modelId={selection.modelId}
                  modelName={selection.modelName}
                  overrides={overrides}
                  onSaved={refreshCartera}
                />
              )}
            </div>
          </div>
        </header>
      )}

      <ViewTransition viewKey={`${view}:${page}`}>
        {view === "portfolio" ? (
          <main className="flex-1 overflow-y-auto p-5 lg:p-8">
            <Dashboard page={page} onOpenAsset={selectAsset} />
          </main>
        ) : (
          <div className="grid flex-1 grid-cols-1 gap-0 lg:grid-cols-[264px_336px_1fr]">
            {/* Left: asset navigator */}
            <aside className="border-r border-slate-200 bg-white p-4">
              <AssetPanel
                selectedModelId={selection?.modelId ?? null}
                selectedAssetId={selection?.assetId ?? null}
                onSelectModel={selectModel}
                onSelectAsset={selectAsset}
                onDeleteAsset={handleDeleteAsset}
              />
            </aside>

            {/* Center: input editor */}
            <section className="border-r border-slate-200 bg-slate-50/80 p-4">
              <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                Parámetros · {selection?.modelName ?? ""}
              </h2>
              {center}
            </section>

            {/* Right: financial output (terminal) */}
            <main className="space-y-5 overflow-y-auto p-5">
              {isEmbed && (
                <div className="flex items-center justify-end gap-3">
                  {recalcBadge}
                  {selection && (
                    <Toolbar
                      modelId={selection.modelId}
                      modelName={selection.modelName}
                      overrides={overrides}
                      onSaved={refreshCartera}
                    />
                  )}
                </div>
              )}

              {selection?.savedAt && (
                <div className="rounded-lg border border-accent-200 bg-accent-50 px-3 py-2 text-xs text-accent-800">
                  Simulación guardada el {fmtDateTime(selection.savedAt)}
                </div>
              )}

              {!result ? (
                <div className="grid h-64 place-items-center text-sm text-slate-400">
                  Calculando…
                </div>
              ) : (
                <>
                  <KpiCards data={result} />
                  {schemaQuery.data && (
                    <CurvesPanel
                      schema={schemaQuery.data}
                      overrides={overrides}
                      onChangeOverride={setOverride}
                    />
                  )}
                  <Charts data={result} />
                  {!hybrid && result.income_statement && (
                    <IncomeStatementTable data={result.income_statement} />
                  )}
                  {!hybrid && result.cash_flow && (
                    <CashFlowTable data={result.cash_flow} />
                  )}
                </>
              )}

              {/* Seguimiento: solo para activos en operación (F2). */}
              {selection?.assetId && selection.lifecycle === "operational" && (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                      Seguimiento operativo
                    </h2>
                    <button
                      type="button"
                      onClick={demoteCurrent}
                      className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
                      title="Devolver este activo a la lista de oportunidades"
                    >
                      Devolver a oportunidad
                    </button>
                  </div>
                  <AssetAlerts assetId={selection.assetId} />
                  <ActualsGrid
                    assetId={selection.assetId}
                    trackingFrequency={selection.trackingFrequency}
                  />
                  <VariancePanel assetId={selection.assetId} />
                  <LivePanel assetId={selection.assetId} />
                </>
              )}
            </main>
          </div>
        )}
      </ViewTransition>
    </div>
  );
}
