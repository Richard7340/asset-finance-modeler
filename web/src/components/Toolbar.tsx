import { useEffect, useState } from "react";
import { downloadExcel } from "../api";

const STORAGE_KEY = "svj_scenarios";

type Scenarios = Record<string, Record<string, number>>;

function loadScenarios(): Scenarios {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export default function Toolbar({
  overrides,
  onLoad,
}: {
  overrides: Record<string, number>;
  onLoad: (overrides: Record<string, number>) => void;
}) {
  const [scenarios, setScenarios] = useState<Scenarios>(loadScenarios);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(scenarios));
  }, [scenarios]);

  const save = () => {
    const n = name.trim();
    if (!n) return;
    setScenarios((prev) => ({ ...prev, [n]: overrides }));
    setName("");
  };

  const remove = (n: string) => {
    setScenarios((prev) => {
      const next = { ...prev };
      delete next[n];
      return next;
    });
  };

  const exportXlsx = async () => {
    setBusy(true);
    try {
      await downloadExcel(overrides);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={exportXlsx}
        disabled={busy}
        className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
      >
        {busy ? "Generando…" : "Descargar Excel"}
      </button>

      <div className="flex items-center gap-1">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre escenario"
          className="w-40 rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          onKeyDown={(e) => e.key === "Enter" && save()}
        />
        <button
          onClick={save}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          Guardar
        </button>
      </div>

      {Object.keys(scenarios).length > 0 && (
        <select
          defaultValue=""
          onChange={(e) => {
            const s = scenarios[e.target.value];
            if (s) onLoad(s);
            e.target.value = "";
          }}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
        >
          <option value="" disabled>
            Cargar escenario…
          </option>
          {Object.keys(scenarios).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      )}

      {Object.keys(scenarios).map((n) => (
        <button
          key={n}
          onClick={() => remove(n)}
          title={`Eliminar ${n}`}
          className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-500 hover:border-rose-300 hover:text-rose-600"
        >
          {n} ✕
        </button>
      ))}
    </div>
  );
}
