import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getModel, isEmbed } from "./api";
import { useRun } from "./hooks/useRun";
import InputsPanel from "./components/InputsPanel";
import KpiCards from "./components/KpiCards";
import Charts from "./components/Charts";
import Toolbar from "./components/Toolbar";

export default function App() {
  const modelQuery = useQuery({ queryKey: ["model"], queryFn: getModel });
  const [overrides, setOverrides] = useState<Record<string, number>>({});

  // Seed overrides with defaults once the model loads.
  const seeded = useMemo(() => {
    if (!modelQuery.data) return false;
    if (Object.keys(overrides).length > 0) return true;
    const defaults: Record<string, number> = {};
    for (const inp of modelQuery.data.inputs) defaults[inp.key] = inp.default;
    setOverrides(defaults);
    return true;
  }, [modelQuery.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isFetching } = useRun(overrides, seeded);

  const setOne = (key: string, value: number) =>
    setOverrides((prev) => ({ ...prev, [key]: value }));

  if (modelQuery.isLoading) {
    return (
      <div className="grid h-full place-items-center text-slate-400">
        Cargando modelo…
      </div>
    );
  }

  if (modelQuery.error || !modelQuery.data) {
    return (
      <div className="grid h-full place-items-center text-rose-500">
        No se pudo cargar el modelo.
      </div>
    );
  }

  const model = modelQuery.data;

  return (
    <div className="min-h-full bg-slate-50 text-slate-900">
      {!isEmbed && (
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-widest text-indigo-600">
                Gestnova · Simulador Financiero
              </div>
              <h1 className="text-lg font-semibold text-slate-800">
                {model.name}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              {isFetching && (
                <span className="flex items-center gap-1.5 text-xs text-slate-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                  recalculando…
                </span>
              )}
              <Toolbar overrides={overrides} onLoad={setOverrides} />
            </div>
          </div>
        </header>
      )}

      <main className="mx-auto max-w-7xl px-6 py-6">
        {isEmbed && (
          <div className="mb-4 flex items-center justify-end gap-3">
            {isFetching && (
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                recalculando…
              </span>
            )}
            <Toolbar overrides={overrides} onLoad={setOverrides} />
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <InputsPanel model={model} overrides={overrides} onChange={setOne} />
          </aside>

          <section className="space-y-6">
            {data ? (
              <>
                <KpiCards data={data} />
                <Charts data={data} />
              </>
            ) : (
              <div className="grid h-64 place-items-center text-slate-400">
                Calculando…
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
