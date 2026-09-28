import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAsset,
  getAsset,
  getSchema,
  isHybridResult,
  isEmbed,
  listAssets,
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
import {
  ArrowLeft,
  Building2,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  SlidersHorizontal,
  Sun,
} from "lucide-react";
import { useRun } from "./hooks/useRun";
import { useTheme } from "./hooks/useTheme";
import { useLayout } from "./hooks/useLayout";
import { useAgentBridge } from "./hooks/useAgentBridge";
import type { AgentBridgeHandlers } from "./hooks/useAgentBridge";
import ResizeDivider from "./components/ResizeDivider";
import { fmtDateTime } from "./format";
import AssetPanel from "./components/AssetPanel";
import Dashboard from "./components/Dashboard";
import type { DashboardPage } from "./components/Dashboard";
import DynamicInputs from "./components/DynamicInputs";
import CurvesPanel from "./components/CurvesPanel";
import Toolbar from "./components/Toolbar";
import ViewTransition from "./components/ViewTransition";
import Ficha from "./components/ficha/Ficha";

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
  const {
    layout,
    setNavWidth,
    setInputsWidth,
    toggleNav,
    toggleInputs,
    isSectionCollapsed,
    toggleSection,
  } = useLayout();
  const [view, setView] = useState<View>("portfolio");
  // Which primary page is active. Cartera (operational) is the landing page.
  const [page, setPage] = useState<DashboardPage>("cartera");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({});
  // La pestaña de la ficha (28-sep): va en la dirección para poder enlazarla.
  const [pestana, setPestana] = useState<string | null>(null);

  const modelId = selection?.modelId ?? null;

  // Report the asset/scenario currently in focus to a host (webOS Portfolio
  // app embeds this UI in an iframe). This lets the agent know what the user is
  // looking at ("modify THIS asset", "simulate what I'm seeing"). It is a safe
  // no-op when not embedded: when there is no distinct parent window
  // (top-level page), window.parent === window and we skip posting.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.parent === window) return; // not embedded → no-op
    try {
      window.parent.postMessage(
        {
          type: "portfolio:state",
          selectedAsset: selection?.assetId ?? null,
          selectedScenarioId: view === "detail" ? page : null,
          modelId: selection?.modelId ?? null,
          assetName: selection?.modelName ?? null,
        },
        "*",
      );
    } catch {
      // Cross-origin or unavailable parent — ignore.
    }
  }, [
    selection?.assetId,
    selection?.modelId,
    selection?.modelName,
    view,
    page,
  ]);

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

  // Select an asset by id OR name (agent bridge: "open THIS asset", and the
  // #/asset/<id> link). Carries lifecycle/tracking from the list, so an
  // operational asset opens with its «Real vs previsto» tab (28-sep).
  const selectAssetById = async (idOrName: string, tab?: string | null) => {
    let lista: SavedAssetSummary[] = [];
    try { lista = await listAssets(); } catch { /* sin lista: por id */ }
    const q = idOrName.trim().toLowerCase();
    const sum = lista.find((x) => x.id === idOrName) ?? lista.find((x) => x.name.toLowerCase() === q) ?? lista.find((x) => x.name.toLowerCase().includes(q));
    const full = await getAsset(sum?.id ?? idOrName);
    setSelection({
      modelId: full.model_id,
      modelName: full.name,
      assetId: full.id,
      savedAt: full.created_at,
      lifecycle: sum?.lifecycle ?? null,
      trackingFrequency: sum?.tracking_frequency ?? null,
    });
    setOverrides(full.overrides ?? {});
    if (sum?.lifecycle === "operational") setPage("cartera");
    else if (sum?.lifecycle === "opportunity") setPage("oportunidades");
    setPestana(tab ?? null);
    setView("detail");
  };

  // ── Direcciones (28-sep): #/cartera, #/oportunidades, #/asset/<id>[/<pestaña>]
  // Se leen al entrar y cuando cambian, y se escriben al navegar, para poder
  // compartir un enlace y volver atrás.
  useEffect(() => {
    const aplicar = () => {
      const h = decodeURIComponent(window.location.hash.replace(/^#\/?/, ""));
      const [a, b, c] = h.split("/");
      if (a === "asset" && b) {
        if (selection?.assetId === b) { if (c) setPestana(c); setView("detail"); }
        else void selectAssetById(b, c ?? null).catch(() => goToPage("cartera"));
      } else if (a === "oportunidades" || a === "cartera") {
        goToPage(a);
      }
    };
    aplicar();
    window.addEventListener("hashchange", aplicar);
    return () => window.removeEventListener("hashchange", aplicar);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const destino = view === "detail" && selection?.assetId
      ? `#/asset/${encodeURIComponent(selection.assetId)}${pestana ? "/" + pestana : ""}`
      : view === "portfolio" ? `#/${page}` : null;
    if (destino && window.location.hash !== destino) {
      try { window.history.replaceState(null, "", destino); } catch { /* sin historial */ }
    }
  }, [view, page, selection?.assetId, pestana]);

  // Force a re-run of the current scenario (used by the agent bridge `run`
  // command). useRun re-simulates automatically on override changes; this
  // covers the explicit "simulate again" with no parameter change by
  // invalidating the cached run.
  const runCurrent = () => {
    if (!modelId) return;
    queryClient.invalidateQueries({ queryKey: ["run", modelId] });
  };

  // Re-fetch the data the embedded UI is showing (parity with backend changes
  // made by the agent via the financial-analysis skill, e.g. createScenario).
  const refreshEmbedded = () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    queryClient.invalidateQueries({ queryKey: ["run"] });
    queryClient.invalidateQueries({ queryKey: ["schema"] });
  };

  // Parent → iframe command bridge: lets the webOS Portfolio app (and through it
  // the agent) operate the LIVE controls of this UI. Applying a command mutates
  // React state, which re-simulates by construction (useRun). set_input also
  // highlights the touched input via the shared spotlight (data-agent-id). Safe
  // no-op when not embedded (the hook never subscribes). Origin/source validated
  // inside the hook (same-origin parent only).
  const agentHandlers = useMemo<AgentBridgeHandlers>(
    () => ({
      setInput: (path, value) => setOverride(path, value),
      run: runCurrent,
      navigate: (section) => {
        if (section === "oportunidades") goToPage("oportunidades");
        else if (section === "cartera") goToPage("cartera");
        else if (["resumen", "real", "curvas", "deuda", "valor", "estados"].includes(section)) setPestana(section);
      },
      selectAsset: (assetId, tab) => selectAssetById(assetId, tab ?? null),
      refresh: refreshEmbedded,
    }),
    // setOverride/goToPage/selectAssetById/runCurrent/refreshEmbedded are stable
    // closures over state setters; modelId is the only value they read that
    // changes. eslint-disable-next-line react-hooks/exhaustive-deps
    [modelId],
  );
  useAgentBridge(agentHandlers);

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
        isSectionCollapsed={isSectionCollapsed}
        toggleSection={toggleSection}
      />
    );
  }, [
    modelId,
    schemaQuery.isLoading,
    schemaQuery.error,
    schemaQuery.data,
    overrides,
    isSectionCollapsed,
    toggleSection,
  ]);

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
            <Dashboard page={page} onOpenAsset={selectAsset} onIrA={goToPage} />
          </main>
        ) : (
          <div className="flex flex-1 flex-col lg:flex-row lg:items-stretch lg:overflow-hidden">
            {/* Left: asset navigator — collapsible to a rail, resizable. */}
            {layout.navCollapsed ? (
              <aside className="flex shrink-0 items-start justify-center border-b border-slate-200 bg-white p-2 lg:w-10 lg:border-b-0 lg:border-r lg:py-3">
                <button
                  type="button"
                  onClick={toggleNav}
                  aria-label="Expandir navegador"
                  title="Expandir navegador"
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
                >
                  <PanelLeftOpen size={16} strokeWidth={2} />
                </button>
              </aside>
            ) : (
              <aside
                className="panel-resizable shrink-0 overflow-y-auto border-b border-slate-200 bg-white p-4 lg:border-b-0 lg:border-r"
                style={{ "--panel-w": `${layout.navWidth}px` } as CSSProperties}
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                    Activos
                  </span>
                  <button
                    type="button"
                    onClick={toggleNav}
                    aria-label="Colapsar navegador"
                    title="Colapsar navegador"
                    className="grid h-7 w-7 place-items-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                  >
                    <PanelLeftClose size={15} strokeWidth={2} />
                  </button>
                </div>
                <AssetPanel
                  selectedModelId={selection?.modelId ?? null}
                  selectedAssetId={selection?.assetId ?? null}
                  onSelectModel={selectModel}
                  onSelectAsset={selectAsset}
                  onDeleteAsset={handleDeleteAsset}
                />
              </aside>
            )}

            {/* Divider: navigator | inputs (only when both visible, lg+). */}
            {!layout.navCollapsed && !layout.inputsCollapsed && (
              <div className="hidden lg:flex">
                <ResizeDivider
                  width={layout.navWidth}
                  onResize={setNavWidth}
                  label="Redimensionar navegador"
                />
              </div>
            )}

            {/* Center: input editor — collapsible to a rail, resizable. */}
            {layout.inputsCollapsed ? (
              <section className="flex shrink-0 items-start justify-center border-b border-slate-200 bg-slate-50/80 p-2 lg:w-10 lg:border-b-0 lg:border-r lg:py-3">
                <button
                  type="button"
                  onClick={toggleInputs}
                  aria-label="Expandir parámetros"
                  title="Expandir parámetros"
                  className="grid h-8 w-8 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
                >
                  <SlidersHorizontal size={16} strokeWidth={2} />
                </button>
              </section>
            ) : (
              <section
                className="panel-resizable shrink-0 overflow-y-auto border-b border-slate-200 bg-slate-50/80 p-4 lg:border-b-0 lg:border-r"
                style={{ "--panel-w": `${layout.inputsWidth}px` } as CSSProperties}
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h2 className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                    Parámetros · {selection?.modelName ?? ""}
                  </h2>
                  <button
                    type="button"
                    onClick={toggleInputs}
                    aria-label="Colapsar parámetros"
                    title="Colapsar parámetros"
                    className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                  >
                    <PanelLeftClose size={15} strokeWidth={2} />
                  </button>
                </div>
                {center}
              </section>
            )}

            {/* Divider: inputs | outputs (when inputs visible, lg+). */}
            {!layout.inputsCollapsed && (
              <div className="hidden lg:flex">
                <ResizeDivider
                  width={layout.inputsWidth}
                  onResize={setInputsWidth}
                  label="Redimensionar parámetros"
                />
              </div>
            )}

            {/* Right: financial output (terminal) — flexes to fill. */}
            <main className="min-w-0 flex-1 space-y-5 overflow-y-auto p-5">
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
                <Ficha
                  key={selection?.assetId ?? modelId ?? "nuevo"}
                  pestana={pestana}
                  onPestana={setPestana}
                  result={result}
                  hybrid={hybrid}
                  assetId={selection?.assetId ?? null}
                  operativo={selection?.lifecycle === "operational"}
                  trackingFrequency={selection?.trackingFrequency ?? null}
                  curvas={schemaQuery.data ? (
                    <CurvesPanel schema={schemaQuery.data} overrides={overrides} onChangeOverride={setOverride} />
                  ) : null}
                  pie={selection?.assetId && selection.lifecycle === "operational" ? (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={demoteCurrent}
                        className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-800"
                        title="Devolver este activo a la lista de oportunidades"
                      >
                        Devolver a oportunidad
                      </button>
                    </div>
                  ) : null}
                />
              )}
            </main>
          </div>
        )}
      </ViewTransition>
    </div>
  );
}
