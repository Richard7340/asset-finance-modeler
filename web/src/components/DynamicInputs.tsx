import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCurves } from "../api";
import type { Curve, ModelSchema, OverrideValue, Overrides, SchemaInput } from "../api";
import { isCurveNameInput, pointsPathFor } from "./CurvesPanel";

type Props = {
  schema: ModelSchema;
  overrides: Overrides;
  /** Sets a numeric override (live recalc). */
  onChangeNumber: (path: string, value: number) => void;
  /** Sets any override value (curve selection / custom points / clears). */
  onChangeOverride: (path: string, value: OverrideValue | undefined) => void;
};

const CUSTOM_CURVE_OPTION = "__custom__";

/** Parse a comma/newline separated list of numbers. */
function parsePoints(raw: string): number[] {
  return raw
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => Number(s))
    .filter((n) => !Number.isNaN(n));
}

/** Dropdown + custom-curve editor for a `..._curve_name` input. */
function CurveSelector({
  inp,
  overrides,
  curves,
  onChangeOverride,
}: {
  inp: SchemaInput;
  overrides: Overrides;
  curves: Curve[];
  onChangeOverride: (path: string, value: OverrideValue | undefined) => void;
}) {
  const pointsPath = pointsPathFor(inp.path);
  const customActive = Array.isArray(overrides[pointsPath]);
  const selected =
    typeof overrides[inp.path] === "string"
      ? (overrides[inp.path] as string)
      : typeof inp.value === "string"
        ? inp.value
        : "";

  // Determine the parameter this input drives (so we can offer matching curves).
  // Prefer the parameter of the curve currently referenced by the schema value.
  const refCurve = curves.find((c) => c.name === selected);
  const parameter = refCurve?.parameter;
  const options = parameter
    ? curves.filter((c) => c.parameter === parameter)
    : curves;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() =>
    customActive ? (overrides[pointsPath] as number[]).join(", ") : "",
  );

  const matched = refCurve;

  const dropdownValue = customActive ? CUSTOM_CURVE_OPTION : selected;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <span
          className="min-w-0 flex-1 truncate text-xs text-slate-600"
          title={inp.path}
        >
          {inp.label && inp.label.trim()
            ? inp.label.charAt(0).toUpperCase() + inp.label.slice(1)
            : inp.path}
        </span>
        <select
          value={dropdownValue}
          onChange={(e) => {
            const v = e.target.value;
            if (v === CUSTOM_CURVE_OPTION) {
              setEditing(true);
              return;
            }
            // Switch to a catalogue curve: set the name, clear any custom points.
            setEditing(false);
            onChangeOverride(pointsPath, undefined);
            onChangeOverride(inp.path, v);
          }}
          className="w-44 rounded border border-slate-300 px-2 py-1 text-sm transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
        >
          {(options.length > 0 ? options : curves).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
          <option value={CUSTOM_CURVE_OPTION}>Curva propia…</option>
        </select>
      </div>

      <div className="text-right text-[11px] text-slate-400">
        {customActive
          ? "Curva propia (valores definidos por el usuario)"
          : matched
            ? matched.source
            : "Fuente no identificada"}
      </div>

      {(editing || customActive) && (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
          <label className="mb-1 block text-[11px] font-medium text-slate-500">
            Valores anuales (separados por coma o salto de línea)
          </label>
          <textarea
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="p.ej. 80, 78, 76, 74, …"
            className="w-full rounded border border-slate-300 px-2 py-1 font-mono text-xs tabular-nums transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                onChangeOverride(pointsPath, undefined);
              }}
              className="rounded px-2 py-1 text-[11px] text-slate-500 transition hover:bg-slate-200"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => {
                const pts = parsePoints(draft);
                if (pts.length === 0) return;
                onChangeOverride(pointsPath, pts);
                setEditing(false);
              }}
              className="rounded bg-accent-600 px-2.5 py-1 text-[11px] font-medium text-white transition hover:bg-accent-700"
            >
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

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
  onChangeOverride,
}: Props) {
  const hasCurveInputs = useMemo(
    () => schema.inputs.some(isCurveNameInput),
    [schema],
  );
  const { data: curvesData } = useQuery({
    queryKey: ["curves"],
    queryFn: () => getCurves(),
    staleTime: 5 * 60 * 1000,
    enabled: hasCurveInputs,
  });
  const curves = curvesData?.curves ?? [];
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
        // Curve selectors get their own control; number inputs are editable
        // live; remaining text/bool are shown read-only.
        const curveInputs = s.inputs.filter(isCurveNameInput);
        const numberInputs = s.inputs.filter((i) => i.type === "number");
        const otherInputs = s.inputs.filter(
          (i) => i.type !== "number" && !isCurveNameInput(i),
        );
        return (
          <div
            key={s.key}
            className="overflow-hidden rounded-lg border border-slate-200 bg-white"
          >
            <button
              type="button"
              onClick={() => setOpen((p) => ({ ...p, [s.key]: !p[s.key] }))}
              className="flex w-full items-center justify-between px-3 py-2 text-left transition hover:bg-slate-50"
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
                {curveInputs.map((inp) => (
                  <CurveSelector
                    key={inp.path}
                    inp={inp}
                    overrides={overrides}
                    curves={curves}
                    onChangeOverride={onChangeOverride}
                  />
                ))}
                {numberInputs.map((inp) => {
                  const ov = overrides[inp.path];
                  const current =
                    typeof ov === "number"
                      ? ov
                      : typeof inp.value === "number"
                        ? inp.value
                        : 0;
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
                        className="w-32 rounded border border-slate-300 px-2 py-1 text-right text-sm tabular-nums transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
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
