import { useMemo, useState } from "react";
import type { ModelSchema, Overrides, SchemaInput } from "../api";

type Props = {
  schema: ModelSchema;
  overrides: Overrides;
  /** Current effective value for a path (override if set, else schema default). */
  onChangeNumber: (path: string, value: number) => void;
};

// Friendlier Spanish-ish titles for known sections; fallback humanizes the key.
const SECTION_TITLES: Record<string, string> = {
  meta: "Configuración",
  timeline: "Calendario",
  production: "Producción",
  degradation: "Degradación",
  revenue: "Ingresos",
  cogs: "Coste de ventas",
  opex: "Gastos operativos",
  capex: "Inversión (CAPEX)",
  working_capital: "Circulante",
  financing: "Financiación",
  valuation: "Valoración",
  taxes: "Impuestos",
};

const SECTION_ORDER = [
  "production",
  "degradation",
  "revenue",
  "cogs",
  "opex",
  "capex",
  "working_capital",
  "financing",
  "valuation",
  "taxes",
  "timeline",
  "meta",
];

function sectionTitle(key: string): string {
  return SECTION_TITLES[key] ?? key.replace(/_/g, " ");
}

function humanLabel(inp: SchemaInput): string {
  const base = inp.label && inp.label.trim() ? inp.label : inp.path;
  return base.charAt(0).toUpperCase() + base.slice(1);
}

export default function DynamicInputs({
  schema,
  overrides,
  onChangeNumber,
}: Props) {
  // Group inputs by section.
  const sections = useMemo(() => {
    const map = new Map<string, SchemaInput[]>();
    for (const inp of schema.inputs) {
      const arr = map.get(inp.section) ?? [];
      arr.push(inp);
      map.set(inp.section, arr);
    }
    const keys = Array.from(map.keys()).sort((a, b) => {
      const ia = SECTION_ORDER.indexOf(a);
      const ib = SECTION_ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    return keys.map((k) => ({ key: k, inputs: map.get(k)! }));
  }, [schema]);

  // First section open by default; meta/timeline collapsed.
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    sections.forEach((s, i) => {
      init[s.key] = i < 4 && s.key !== "meta" && s.key !== "timeline";
    });
    return init;
  });

  return (
    <div className="space-y-2">
      {sections.map((s) => {
        const isOpen = open[s.key] ?? false;
        // Only number inputs are editable live; text/bool are shown read-only.
        const numberInputs = s.inputs.filter((i) => i.type === "number");
        const otherInputs = s.inputs.filter((i) => i.type !== "number");
        return (
          <div
            key={s.key}
            className="overflow-hidden rounded-lg border border-slate-200 bg-white"
          >
            <button
              type="button"
              onClick={() => setOpen((p) => ({ ...p, [s.key]: !p[s.key] }))}
              className="flex w-full items-center justify-between px-3 py-2 text-left"
            >
              <span className="text-sm font-semibold text-slate-700">
                {sectionTitle(s.key)}
              </span>
              <span className="text-xs text-slate-400">
                {s.inputs.length} · {isOpen ? "−" : "+"}
              </span>
            </button>
            {isOpen && (
              <div className="space-y-2 border-t border-slate-100 px-3 py-3">
                {numberInputs.map((inp) => {
                  const current =
                    overrides[inp.path] ??
                    (typeof inp.value === "number" ? inp.value : 0);
                  return (
                    <label
                      key={inp.path}
                      className="flex items-center justify-between gap-3"
                    >
                      <span
                        className="min-w-0 flex-1 truncate text-xs text-slate-600"
                        title={inp.path}
                      >
                        {humanLabel(inp)}
                      </span>
                      <input
                        type="number"
                        step="any"
                        value={current}
                        onChange={(e) => {
                          const v = e.target.valueAsNumber;
                          onChangeNumber(
                            inp.path,
                            Number.isNaN(v) ? 0 : v,
                          );
                        }}
                        className="w-32 rounded border border-slate-300 px-2 py-1 text-right text-sm tabular-nums focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                      />
                    </label>
                  );
                })}
                {otherInputs.map((inp) => (
                  <div
                    key={inp.path}
                    className="flex items-center justify-between gap-3"
                  >
                    <span
                      className="min-w-0 flex-1 truncate text-xs text-slate-500"
                      title={inp.path}
                    >
                      {humanLabel(inp)}
                    </span>
                    <span className="w-32 truncate text-right text-xs text-slate-400">
                      {String(inp.value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
