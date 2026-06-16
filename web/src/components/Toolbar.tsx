import { useState } from "react";
import { MapPin } from "lucide-react";
import { canExport, downloadExcel, saveAsset } from "../api";
import type { AssetLocation, Overrides } from "../api";

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

  // Optional location for the portfolio map (F4-2).
  const [showLoc, setShowLoc] = useState(false);
  const [loc, setLoc] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");

  const exportable = canExport(modelId);

  const locationPayload = (): AssetLocation | undefined => {
    const latN = lat.trim() === "" ? null : Number(lat);
    const lonN = lon.trim() === "" ? null : Number(lon);
    const locS = loc.trim() === "" ? null : loc.trim();
    if (locS === null && latN === null && lonN === null) return undefined;
    return {
      location: locS,
      lat: latN != null && Number.isFinite(latN) ? latN : null,
      lon: lonN != null && Number.isFinite(lonN) ? lonN : null,
    };
  };

  const save = async () => {
    const n = name.trim() || `${modelName} ${new Date().toLocaleDateString("es-ES")}`;
    setSavingState("busy");
    setNotice(null);
    try {
      await saveAsset(modelId, n, overrides, locationPayload());
      setName("");
      setLoc("");
      setLat("");
      setLon("");
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
        onClick={() => setShowLoc((s) => !s)}
        aria-pressed={showLoc}
        title="Ubicación (opcional, para el mapa)"
        className={`grid h-8 w-8 place-items-center rounded-md border transition ${
          showLoc
            ? "border-accent-500 bg-accent-50 text-accent-700"
            : "border-slate-300 bg-white text-slate-500 hover:bg-slate-50"
        }`}
      >
        <MapPin size={15} strokeWidth={2} />
      </button>
      <button
        type="button"
        onClick={save}
        disabled={savingState === "busy"}
        className="rounded-md bg-accent-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-accent-700 disabled:opacity-50"
      >
        {savingState === "busy" ? "Guardando…" : savingState === "ok" ? "Guardado" : "Guardar"}
      </button>

      {showLoc && (
        <div className="flex w-full flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-slate-50/80 p-2">
          <input
            value={loc}
            onChange={(e) => setLoc(e.target.value)}
            placeholder="Ubicación (texto)"
            className="w-44 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-900 transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
          <input
            value={lat}
            onChange={(e) => setLat(e.target.value)}
            inputMode="decimal"
            placeholder="Lat"
            className="w-24 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm tabular-nums text-slate-900 transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
          <input
            value={lon}
            onChange={(e) => setLon(e.target.value)}
            inputMode="decimal"
            placeholder="Lon"
            className="w-24 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm tabular-nums text-slate-900 transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
          <span className="text-[11px] text-slate-400">
            Coordenadas decimales (p. ej. 37.39, -5.99). Solo para el mapa.
          </span>
        </div>
      )}

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
