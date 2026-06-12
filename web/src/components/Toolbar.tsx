import { useState } from "react";
import { canExport, downloadExcel, saveAsset } from "../api";
import type { Overrides } from "../api";

type Props = {
  modelId: string;
  modelName: string;
  overrides: Overrides;
  onSaved: () => void;
};

export default function Toolbar({ modelId, modelName, overrides, onSaved }: Props) {
  const [name, setName] = useState("");
  const [savingState, setSavingState] = useState<"idle" | "busy" | "ok">("idle");
  const [exportBusy, setExportBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const exportable = canExport(modelId);

  const save = async () => {
    const n = name.trim() || `${modelName} ${new Date().toLocaleDateString("es-ES")}`;
    setSavingState("busy");
    setNotice(null);
    try {
      await saveAsset(modelId, n, overrides);
      setName("");
      setSavingState("ok");
      onSaved();
      setTimeout(() => setSavingState("idle"), 1500);
    } catch (e) {
      setSavingState("idle");
      setNotice(e instanceof Error ? e.message : "No se pudo guardar.");
    }
  };

  const exportXlsx = async () => {
    setExportBusy(true);
    setNotice(null);
    try {
      await downloadExcel(modelId, overrides);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "No se pudo exportar.");
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nombre de la simulación"
        onKeyDown={(e) => e.key === "Enter" && save()}
        className="w-48 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-900 transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
      />
      <button
        type="button"
        onClick={save}
        disabled={savingState === "busy"}
        className="rounded-md bg-accent-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-accent-700 disabled:opacity-50"
      >
        {savingState === "busy" ? "Guardando…" : savingState === "ok" ? "Guardado" : "Guardar"}
      </button>

      {exportable && (
        <button
          type="button"
          onClick={exportXlsx}
          disabled={exportBusy}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          {exportBusy ? "Generando…" : "Descargar Excel"}
        </button>
      )}

      {notice && <span className="text-xs text-rose-600">{notice}</span>}
    </div>
  );
}
