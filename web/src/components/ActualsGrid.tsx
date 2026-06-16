import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { deleteActual, getActuals, getLines, postActuals } from "../api";
import type { TrackingFrequency } from "../api";
import { fmtDate } from "../format";

type Props = {
  assetId: string;
  trackingFrequency: TrackingFrequency | null;
};

const FREQ_LABEL: Record<TrackingFrequency, string> = {
  daily: "diaria",
  monthly: "mensual",
  quarterly: "trimestral",
};

/** Today as a YYYY-MM-DD string (input[type=date] format). */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * "Datos reales" — entry grid for an operational asset. Lets the user pick a
 * trackable model line and record a real value per period (date + value +
 * optional unit/note). On save it invalidates the actuals/variance queries so
 * the variance panel updates. Lists existing actuals with delete.
 */
export default function ActualsGrid({ assetId, trackingFrequency }: Props) {
  const queryClient = useQueryClient();

  const linesQuery = useQuery({
    queryKey: ["lines", assetId],
    queryFn: () => getLines(assetId),
  });

  const [linePath, setLinePath] = useState<string>("");
  const selectedLine = useMemo(
    () => linesQuery.data?.find((l) => l.path === linePath),
    [linesQuery.data, linePath],
  );

  // Default the selector to the first line once lines load.
  const effectiveLine = linePath || linesQuery.data?.[0]?.path || "";

  const actualsQuery = useQuery({
    queryKey: ["actuals", assetId, effectiveLine],
    queryFn: () => getActuals(assetId, { linePath: effectiveLine }),
    enabled: !!effectiveLine,
  });

  const [period, setPeriod] = useState<string>(todayIso());
  const [value, setValue] = useState<string>("");
  const [unit, setUnit] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["actuals", assetId] });
    queryClient.invalidateQueries({ queryKey: ["variance", assetId] });
    queryClient.invalidateQueries({ queryKey: ["live", assetId] });
  };

  const addMutation = useMutation({
    mutationFn: () =>
      postActuals(assetId, [
        {
          period_start: period,
          line_path: effectiveLine,
          value: Number(value),
          unit: unit || selectedLine?.unit || "",
          note: note || undefined,
        },
      ]),
    onSuccess: () => {
      setValue("");
      setNote("");
      setError(null);
      invalidate();
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "Error al guardar"),
  });

  const delMutation = useMutation({
    mutationFn: (id: string) => deleteActual(assetId, id),
    onSuccess: invalidate,
  });

  const submit = () => {
    if (!effectiveLine) {
      setError("Selecciona una línea.");
      return;
    }
    if (value.trim() === "" || !Number.isFinite(Number(value))) {
      setError("Introduce un valor numérico.");
      return;
    }
    if (!period) {
      setError("Introduce una fecha.");
      return;
    }
    addMutation.mutate();
  };

  if (linesQuery.isLoading) {
    return <div className="p-2 text-sm text-slate-400">Cargando líneas…</div>;
  }
  if (linesQuery.error || !linesQuery.data || linesQuery.data.length === 0) {
    return (
      <div className="p-2 text-sm text-slate-400">
        No hay líneas trackeables para este activo.
      </div>
    );
  }

  const actuals = actualsQuery.data ?? [];
  const unitHint = selectedLine?.unit || linesQuery.data[0]?.unit || "";

  return (
    <section className="surface p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">Datos reales</h3>
        {trackingFrequency && (
          <span className="text-[11px] text-slate-400">
            Frecuencia {FREQ_LABEL[trackingFrequency]}
          </span>
        )}
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Registra el dato real observado por periodo para cada línea del modelo.
        Se compara con el caso base congelado en el panel de varianza.
      </p>

      {/* Line selector */}
      <label className="mb-3 block">
        <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
          Línea
        </span>
        <select
          aria-label="Línea a registrar"
          value={effectiveLine}
          onChange={(e) => {
            setLinePath(e.target.value);
            setUnit("");
          }}
          className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
        >
          {linesQuery.data.map((l) => (
            <option key={l.path} value={l.path}>
              {l.label}
              {l.unit ? ` (${l.unit})` : ""}
            </option>
          ))}
        </select>
      </label>

      {/* Entry row */}
      <div className="mb-2 flex flex-wrap items-end gap-2 rounded-md border border-slate-200 bg-slate-50 p-2">
        <div className="flex flex-col">
          <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Fecha
          </label>
          <input
            aria-label="Fecha del periodo"
            type="date"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 text-xs focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
        </div>
        <div className="flex flex-col">
          <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Valor
          </label>
          <input
            aria-label="Valor real"
            type="number"
            step="any"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-28 rounded border border-slate-300 px-2 py-1 text-right text-xs tabular-nums focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
        </div>
        <div className="flex flex-col">
          <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Unidad
          </label>
          <input
            aria-label="Unidad"
            type="text"
            value={unit}
            placeholder={unitHint || "—"}
            onChange={(e) => setUnit(e.target.value)}
            className="w-20 rounded border border-slate-300 px-2 py-1 text-xs focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
        </div>
        <div className="flex min-w-[8rem] flex-1 flex-col">
          <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Nota
          </label>
          <input
            aria-label="Nota"
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-xs focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={addMutation.isPending}
          className="flex items-center gap-1 rounded bg-accent-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-700 disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          {addMutation.isPending ? "Guardando…" : "Añadir"}
        </button>
      </div>

      {error && <div className="mb-2 text-xs text-rose-600">{error}</div>}

      {/* Existing actuals */}
      {actualsQuery.isLoading ? (
        <div className="p-2 text-xs text-slate-400">Cargando datos…</div>
      ) : actuals.length === 0 ? (
        <div className="p-2 text-xs text-slate-400">
          Aún no hay datos reales para esta línea.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[10px] uppercase tracking-wide text-slate-400">
                <th className="py-1.5 pr-2 font-medium">Fecha</th>
                <th className="py-1.5 pr-2 text-right font-medium">Valor</th>
                <th className="py-1.5 pr-2 font-medium">Unidad</th>
                <th className="py-1.5 pr-2 font-medium">Nota</th>
                <th className="py-1.5 pr-2" />
              </tr>
            </thead>
            <tbody>
              {actuals.map((a) => (
                <tr key={a.id} className="border-b border-slate-100">
                  <td className="py-1.5 pr-2 tabular-nums text-slate-600">
                    {fmtDate(a.period_start)}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-900">
                    {a.value.toLocaleString("es-ES")}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-500">{a.unit || "—"}</td>
                  <td className="py-1.5 pr-2 text-slate-500">{a.note || "—"}</td>
                  <td className="py-1.5 pr-2 text-right">
                    <button
                      type="button"
                      aria-label={`Borrar dato del ${a.period_start}`}
                      onClick={() => delMutation.mutate(a.id)}
                      className="rounded p-1 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
