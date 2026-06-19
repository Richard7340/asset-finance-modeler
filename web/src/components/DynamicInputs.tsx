import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
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
  /**
   * Persisted per-section collapse, wired from the layout store. `fallback` is
   * the default-expanded heuristic (first sections open, meta/timeline closed).
   * Optional: when omitted (e.g. in unit tests) the component manages its own
   * collapse state internally.
   */
  isSectionCollapsed?: (key: string, fallback: boolean) => boolean;
  toggleSection?: (key: string, fallback: boolean) => void;
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
          data-agent-id={`asset.${inp.path}`}
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

/** Parent object prefix of a path, e.g. `revenue[0].base_price` → `revenue[0]`. */
function parentPrefix(path: string): string {
  const i = path.lastIndexOf(".");
  return i === -1 ? "" : path.slice(0, i);
}

// Scalar leaf-name tokens whose value is superseded when a sibling price curve
// is active (backend precedence: curve_name > points > scalar). Used only to
// flag the affected scalars, not to disable unrelated siblings (volume, etc.).
const CURVE_GOVERNED_TOKENS = ["price", "spread", "capture", "escalation"];

/**
 * For every parent prefix that has an active curve (a non-empty `*_curve_name`
 * — from override or schema default — or a `*_points` override array), the
 * sibling price-family scalars are overridden by the curve. Returns the set of
 * those prefixes so the affected scalar inputs can show a "definido por la
 * curva" hint and be de-emphasized.
 */
function activeCurvePrefixes(
  schema: ModelSchema,
  overrides: Overrides,
): Set<string> {
  const out = new Set<string>();
  for (const inp of schema.inputs) {
    if (!isCurveNameInput(inp)) continue;
    const prefix = parentPrefix(inp.path);
    const pointsPath = pointsPathFor(inp.path);
    const nameOv = overrides[inp.path];
    const pointsActive = Array.isArray(overrides[pointsPath]);
    const nameActive =
      typeof nameOv === "string"
        ? nameOv.length > 0
        : typeof inp.value === "string" && inp.value.length > 0;
    if (nameActive || pointsActive) out.add(prefix);
  }
  return out;
}

/** True if `inp` is a price-family scalar superseded by an active sibling curve. */
function isGovernedByCurve(inp: SchemaInput, prefixes: Set<string>): boolean {
  if (inp.type !== "number") return false;
  if (!prefixes.has(parentPrefix(inp.path))) return false;
  const leaf = inp.path.split(".").pop() ?? inp.path;
  return CURVE_GOVERNED_TOKENS.some((t) => leaf.includes(t));
}

export default function DynamicInputs({
  schema,
  overrides,
  onChangeNumber,
  onChangeOverride,
  isSectionCollapsed,
  toggleSection,
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
  // Prefixes whose price-family scalars are superseded by an active curve.
  const curvePrefixes = useMemo(
    () => activeCurvePrefixes(schema, overrides),
    [schema, overrides],
  );
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

  // Default-expanded heuristic: first sections open, meta/timeline closed.
  const defaultOpen = useMemo(() => {
    const m: Record<string, boolean> = {};
    sections.forEach((s, i) => {
      m[s.key] = i < 4 && s.key !== "meta" && s.key !== "timeline";
    });
    return m;
  }, [sections]);

  // Fallback to internal state when the layout store isn't wired (tests).
  const [internalOpen, setInternalOpen] = useState<Record<string, boolean>>({});
  const sectionOpen = (key: string): boolean => {
    if (isSectionCollapsed) return !isSectionCollapsed(key, !defaultOpen[key]);
    const v = internalOpen[key];
    return v === undefined ? !!defaultOpen[key] : v;
  };
  const onToggleSection = (key: string) => {
    if (toggleSection) {
      toggleSection(key, !defaultOpen[key]);
      return;
    }
    setInternalOpen((p) => ({
      ...p,
      [key]: !(p[key] === undefined ? !!defaultOpen[key] : p[key]),
    }));
  };

  return (
    <div className="space-y-2">
      {sections.map((s) => {
        const isOpen = sectionOpen(s.key);
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
              onClick={() => onToggleSection(s.key)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between px-3 py-2 text-left transition hover:bg-slate-50"
            >
              <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                {isOpen ? (
                  <ChevronDown size={14} strokeWidth={2} className="text-slate-400" />
                ) : (
                  <ChevronRight size={14} strokeWidth={2} className="text-slate-400" />
                )}
                {sectionTitle(s.key)}
              </span>
              <span className="text-xs text-slate-400">{s.inputs.length}</span>
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
                  const governed = isGovernedByCurve(inp, curvePrefixes);
                  return (
                    <label
                      key={inp.path}
                      className={`flex items-center justify-between gap-3 ${
                        governed ? "opacity-60" : ""
                      }`}
                    >
                      <span
                        className="min-w-0 flex-1 text-xs text-slate-600"
                        title={inp.path}
                      >
                        <span className="block truncate">{humanLabel(inp)}</span>
                        {governed && (
                          <span className="block text-[10px] font-normal text-slate-400">
                            definido por la curva
                          </span>
                        )}
                      </span>
                      <input
                        type="number"
                        step="any"
                        data-agent-id={`asset.${inp.path}`}
                        value={current}
                        title={
                          governed
                            ? "Una curva activa define este valor; edita la curva para cambiarlo."
                            : undefined
                        }
                        onChange={(e) => {
                          const v = e.target.valueAsNumber;
                          // Clearing the field (NaN) removes the override so the
                          // input reverts to the schema default — not a forced 0.
                          if (Number.isNaN(v)) {
                            onChangeOverride(inp.path, undefined);
                          } else {
                            onChangeNumber(inp.path, v);
                          }
                        }}
                        className="w-32 rounded border border-slate-300 px-2 py-1 text-right text-sm tabular-nums transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
                      />
                    </label>
                  );
                })}
                {otherInputs.map((inp) => {
                  const ov = overrides[inp.path];
                  if (inp.type === "bool") {
                    const checked =
                      typeof ov === "boolean"
                        ? ov
                        : typeof inp.value === "boolean"
                          ? inp.value
                          : false;
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
                          type="checkbox"
                          role="switch"
                          data-agent-id={`asset.${inp.path}`}
                          aria-label={humanLabel(inp)}
                          checked={checked}
                          onChange={(e) =>
                            onChangeOverride(inp.path, e.target.checked)
                          }
                          className="h-4 w-4 rounded border-slate-300 text-accent-600 transition focus:ring-1 focus:ring-accent-500"
                        />
                      </label>
                    );
                  }
                  // text / enum: free-text input (live override on change).
                  const text =
                    typeof ov === "string"
                      ? ov
                      : ov == null && typeof inp.value === "string"
                        ? inp.value
                        : inp.value == null
                          ? ""
                          : String(inp.value);
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
                        type="text"
                        data-agent-id={`asset.${inp.path}`}
                        aria-label={humanLabel(inp)}
                        value={text}
                        onChange={(e) => {
                          const v = e.target.value;
                          // Empty string clears the override (revert to default);
                          // otherwise commit the string value.
                          onChangeOverride(
                            inp.path,
                            v.length === 0 ? undefined : v,
                          );
                        }}
                        className="w-32 truncate rounded border border-slate-300 px-2 py-1 text-right text-sm transition focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
                      />
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
