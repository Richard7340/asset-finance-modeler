import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { animate } from "animejs";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCurves } from "../api";
import type {
  Curve,
  ModelSchema,
  OverrideValue,
  Overrides,
  SchemaInput,
} from "../api";

type Props = {
  schema: ModelSchema;
  overrides: Overrides;
  /** Sets any override value (custom points / clears). Enables edit mode. */
  onChangeOverride?: (path: string, value: OverrideValue | undefined) => void;
};

const CURVE_NAME_SUFFIX = "curve_name";
const HORIZON = 30;

const C = {
  accent: "#4f46e5",
  slate: "#94a3b8",
  grid: "#eef2f7",
};
const AXIS = { fontSize: 11, fill: "#64748b" };
const tooltipStyle = {
  fontSize: 12,
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  boxShadow: "0 6px 24px rgb(15 23 42 / 0.10)",
  padding: "8px 10px",
};

/** True for inputs that select a price curve (path ends with `..._curve_name`). */
export function isCurveNameInput(inp: SchemaInput): boolean {
  return inp.path.endsWith(CURVE_NAME_SUFFIX) && typeof inp.value === "string";
}

/** `a.b.spread_curve_name` → `a.b.spread_points`. */
export function pointsPathFor(curveNamePath: string): string {
  return curveNamePath.replace(/curve_name$/, "points");
}

function fieldLabel(inp: SchemaInput): string {
  const base = inp.label && inp.label.trim() ? inp.label : inp.path;
  return base.charAt(0).toUpperCase() + base.slice(1);
}

/**
 * Derive a human axis unit from a parameter id, e.g. `spread_eur_mwh` →
 * "EUR/MWh", `price_usd_kg` → "USD/kg". Generic across asset types; falls back
 * to no unit when the parameter has no currency/measure tokens.
 */
export function unitFromParameter(parameter?: string): string {
  if (!parameter) return "";
  const tokens = parameter.toLowerCase().split(/[_\s]+/);
  const cur: Record<string, string> = { eur: "EUR", usd: "USD", gbp: "GBP" };
  const measure: Record<string, string> = {
    mwh: "MWh",
    kwh: "kWh",
    mw: "MW",
    kg: "kg",
    t: "t",
    ton: "t",
    unit: "ud",
    pct: "%",
  };
  let currency = "";
  let perUnit = "";
  for (const t of tokens) {
    if (!currency && cur[t]) currency = cur[t];
    if (!perUnit && measure[t]) perUnit = measure[t];
  }
  if (currency && perUnit) return `${currency}/${perUnit}`;
  if (currency) return currency;
  if (perUnit) return perUnit;
  return "";
}

/** Pad/trim an array to exactly `HORIZON` numeric values. */
function toHorizon(values: number[] | undefined): number[] {
  const src = values ?? [];
  const out: number[] = [];
  for (let i = 0; i < HORIZON; i += 1) {
    const v = src[i];
    out.push(typeof v === "number" && Number.isFinite(v) ? v : (src[src.length - 1] ?? 0));
  }
  return out;
}

/**
 * "Curvas de mercado y fuentes" — for every curve-driven input in the current
 * model, shows the selected curve, its consultant source, an editable 30-year
 * chart and a bankability tag. Editing applies a custom `*_points` override.
 */
export default function CurvesPanel({ schema, overrides, onChangeOverride }: Props) {
  const curveInputs = useMemo(
    () => schema.inputs.filter(isCurveNameInput),
    [schema],
  );

  const { data } = useQuery({
    queryKey: ["curves"],
    queryFn: () => getCurves(),
    staleTime: 5 * 60 * 1000,
    enabled: curveInputs.length > 0,
  });

  if (curveInputs.length === 0) return null;

  const curves = data?.curves ?? [];

  return (
    <section className="surface p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">
          Curvas de mercado y fuentes
        </h3>
        <span className="text-[11px] text-slate-400">Proyección a 30 años</span>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Curvas de consultor que alimentan las proyecciones. Edita la proyección
        año a año para simular tu propio escenario.
      </p>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {curveInputs.map((inp) => {
          const pointsPath = pointsPathFor(inp.path);
          const customPoints = overrides[pointsPath];
          const custom = Array.isArray(customPoints);
          const selectedName =
            typeof overrides[inp.path] === "string"
              ? (overrides[inp.path] as string)
              : typeof inp.value === "string"
                ? inp.value
                : "";
          const matched = curves.find((c) => c.name === selectedName);
          return (
            <CurveCardResolved
              key={inp.path}
              inp={inp}
              matched={matched}
              custom={custom}
              customPoints={custom ? (customPoints as number[]) : undefined}
              selectedName={selectedName}
              onChangeOverride={onChangeOverride}
            />
          );
        })}
      </div>
    </section>
  );
}

/** Resolved card: receives the already-matched curve / custom state. */
function CurveCardResolved({
  inp,
  matched,
  custom,
  customPoints,
  selectedName,
  onChangeOverride,
}: {
  inp: SchemaInput;
  matched: Curve | undefined;
  custom: boolean;
  customPoints: number[] | undefined;
  selectedName: string;
  onChangeOverride?: (path: string, value: OverrideValue | undefined) => void;
}) {
  const pointsPath = pointsPathFor(inp.path);
  const parameter = matched?.parameter ?? inp.path.split(".").slice(-2)[0];
  const unit = unitFromParameter(matched?.parameter);
  const editable = typeof onChangeOverride === "function";

  // Source-of-truth values shown when not actively editing.
  const baseValues = useMemo(
    () =>
      custom
        ? toHorizon(customPoints)
        : matched
          ? toHorizon(matched.values)
          : [],
    [custom, customPoints, matched],
  );

  const [editing, setEditing] = useState(false);
  // Local working array used while editing.
  const [working, setWorking] = useState<number[]>(baseValues);
  const [focusYear, setFocusYear] = useState<number | null>(null);
  const [pct, setPct] = useState("");
  const [base, setBase] = useState("");

  const gridRef = useRef<HTMLDivElement | null>(null);
  const cellRefs = useRef<Array<HTMLInputElement | null>>([]);
  const editPanelRef = useRef<HTMLDivElement | null>(null);

  // ---- Drag-to-edit on the chart --------------------------------------
  // Index of the year currently being dragged (null = no drag in progress).
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  // Linear map from a screen Y pixel to a value, captured at pointerdown so
  // the mapping is stable for the whole drag gesture. Derived from two
  // rendered dots (their exact recharts cy/value pairs), which inherently
  // captures the plot-area bounds, axis margins and Y-domain padding.
  const pixelToValueRef = useRef<((clientY: number) => number) | null>(null);
  // Live record of every rendered dot: screen-space Y pixel + its value.
  // Keyed by year index; refreshed by the custom dot renderer each paint.
  const dotsRef = useRef<Map<number, { pageY: number; value: number }>>(new Map());
  // Plot-area screen bounds (top/bottom in clientY), used as a fallback scale.
  const chartBoundsRef = useRef<{ top: number; bottom: number } | null>(null);

  // A sane value domain for clamping (>= 0): current working range padded.
  const valueDomain = useMemo(() => {
    const vals = (editing ? working : baseValues).filter((v) => Number.isFinite(v));
    if (vals.length === 0) return { min: 0, max: 1 };
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const span = hi - lo || Math.abs(hi) || 1;
    const pad = span * 0.15;
    return { min: Math.max(0, lo - pad), max: hi + pad };
  }, [editing, working, baseValues]);

  // Re-seed the working array whenever we (re)enter edit mode or the underlying
  // curve changes while not editing.
  useEffect(() => {
    if (!editing) setWorking(baseValues);
  }, [editing, baseValues]);

  // Subtle reveal of the editor panel.
  useEffect(() => {
    if (editing && editPanelRef.current) {
      animate(editPanelRef.current, {
        opacity: [0, 1],
        translateY: [-4, 0],
        duration: 220,
        ease: "outQuad",
      });
    }
  }, [editing]);

  // Focus the selected year's input when a chart point is clicked.
  useEffect(() => {
    if (focusYear == null) return;
    const el = cellRefs.current[focusYear - 1];
    if (el) {
      el.focus();
      el.select();
    }
  }, [focusYear]);

  const liveValues = editing ? working : baseValues;
  const chartData = liveValues.map((v, i) => ({ year: i + 1, value: v }));
  const showChart = chartData.length > 0;

  // Custom dot: records its live screen-space position (for the drag scale)
  // and, in edit mode, renders a generous transparent hit target so points
  // are easy to grab and drag vertically. Returns a plain SVG group.
  type DotProps = {
    cx?: number;
    cy?: number;
    index?: number;
    payload?: { value: number };
  };
  const renderDot = (props: DotProps) => {
    const { cx, cy, index, payload } = props;
    if (cx == null || cy == null || index == null) {
      return <g key={`dot-empty-${index ?? Math.random()}`} />;
    }
    const value = payload?.value ?? 0;
    const dragging = dragIndex === index;
    const recordPos = (el: SVGCircleElement | null) => {
      if (!el) {
        dotsRef.current.delete(index);
        return;
      }
      const r = el.getBoundingClientRect();
      dotsRef.current.set(index, { pageY: r.top + r.height / 2, value });
      // Capture plot band bounds from the owning SVG for the fallback scale.
      const svg = el.ownerSVGElement;
      if (svg) {
        const sr = svg.getBoundingClientRect();
        chartBoundsRef.current = { top: sr.top + 6, bottom: sr.bottom - 6 };
      }
    };
    return (
      <g key={`dot-${index}`}>
        <circle
          ref={recordPos}
          cx={cx}
          cy={cy}
          r={dragging ? 4.5 : 2.5}
          fill={dragging ? C.accent : "#fff"}
          stroke={C.accent}
          strokeWidth={1.5}
        />
        {editing && (
          <circle
            cx={cx}
            cy={cy}
            r={9}
            fill="transparent"
            style={{ cursor: "ns-resize", touchAction: "none" }}
            onPointerDown={(e) => onDotPointerDown(index, e)}
          />
        )}
      </g>
    );
  };

  const setCell = (index: number, raw: number) => {
    setWorking((prev) => {
      const next = prev.slice();
      next[index] = Number.isFinite(raw) ? raw : 0;
      return next;
    });
  };

  const applyGrowth = () => {
    const rate = Number(pct);
    if (!Number.isFinite(rate)) return;
    const factor = 1 + rate / 100;
    const start =
      Number.isFinite(Number(base)) && base.trim() !== ""
        ? Number(base)
        : (working[0] ?? 0);
    setWorking(() => {
      const out: number[] = [];
      let v = start;
      for (let i = 0; i < HORIZON; i += 1) {
        out.push(Number(v.toFixed(4)));
        v *= factor;
      }
      return out;
    });
  };

  const setBaseYearOne = () => {
    const v = Number(base);
    if (!Number.isFinite(v) || base.trim() === "") return;
    setWorking((prev) => {
      const next = prev.length === HORIZON ? prev.slice() : toHorizon(prev);
      next[0] = v;
      return next;
    });
  };

  // Build the pixel->value scale for the active drag from the rendered dots.
  // Uses the two dots with the largest Y separation for numerical stability;
  // falls back to the plot-area bounds + value domain if only one dot is known.
  const buildPixelToValue = (): ((clientY: number) => number) => {
    const dots = Array.from(dotsRef.current.values());
    if (dots.length >= 2) {
      let a = dots[0];
      let b = dots[1];
      for (let i = 0; i < dots.length; i += 1) {
        for (let j = i + 1; j < dots.length; j += 1) {
          if (Math.abs(dots[i].pageY - dots[j].pageY) > Math.abs(a.pageY - b.pageY)) {
            a = dots[i];
            b = dots[j];
          }
        }
      }
      const dPix = b.pageY - a.pageY;
      if (Math.abs(dPix) > 0.5) {
        const slope = (b.value - a.value) / dPix; // value units per pixel
        return (clientY: number) => a.value + (clientY - a.pageY) * slope;
      }
    }
    // Fallback: map the visible plot band linearly onto the value domain.
    const band = chartBoundsRef.current;
    if (band) {
      const { top, bottom } = band;
      const { min, max } = valueDomain;
      return (clientY: number) => {
        const frac = (bottom - clientY) / Math.max(1, bottom - top);
        return min + frac * (max - min);
      };
    }
    return (_clientY: number) => working[dragIndex ?? 0] ?? 0;
  };

  const onDotPointerDown = (index: number, e: React.PointerEvent) => {
    if (!editing) return;
    e.stopPropagation();
    e.preventDefault();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setFocusYear(index + 1);
    setDragIndex(index);
    pixelToValueRef.current = buildPixelToValue();
  };

  // Window-level move/up so the drag survives leaving the dot's hit area.
  useEffect(() => {
    if (dragIndex == null) return;
    const onMove = (e: PointerEvent) => {
      const map = pixelToValueRef.current;
      if (!map) return;
      const raw = map(e.clientY);
      const clamped = Math.max(0, Number.isFinite(raw) ? raw : 0);
      const rounded = Number(clamped.toFixed(4));
      setWorking((prev) => {
        if (prev[dragIndex] === rounded) return prev;
        const next = prev.slice();
        next[dragIndex] = rounded;
        return next;
      });
    };
    const onUp = () => {
      setDragIndex(null);
      pixelToValueRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dragIndex]);

  const apply = () => {
    if (!onChangeOverride) return;
    onChangeOverride(pointsPath, toHorizon(working));
    setEditing(false);
  };

  const restore = () => {
    if (!onChangeOverride) return;
    // Clear both the custom points and any curve_name override so the card
    // reverts to the library curve referenced by the schema.
    onChangeOverride(pointsPath, undefined);
    onChangeOverride(inp.path, undefined);
    setEditing(false);
    setPct("");
    setBase("");
  };

  return (
    <div
      className={`surface-hover rounded-lg border p-4 transition ${
        editing ? "border-accent-300 ring-1 ring-accent-200" : "border-slate-200"
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div
            className="truncate text-sm font-semibold text-slate-800"
            title={inp.path}
          >
            {fieldLabel(inp)}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">
            {parameter}
            {unit ? ` · ${unit}` : ""}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!custom && matched && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                matched.bankable
                  ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
              }`}
            >
              {matched.bankable ? "Bankable" : "No bankable"}
            </span>
          )}
          {editable && baseValues.length > 0 && (
            <button
              type="button"
              onClick={() => setEditing((e) => !e)}
              aria-pressed={editing}
              className={`rounded border px-2 py-0.5 text-[11px] font-medium transition ${
                editing
                  ? "border-accent-300 bg-accent-50 text-accent-700"
                  : "border-slate-300 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {editing ? "Editando" : "Editar proyección"}
            </button>
          )}
        </div>
      </div>

      <div className="mb-1 text-sm font-medium text-slate-900">
        {custom
          ? "Curva propia (editada por el usuario)"
          : (matched?.name ?? (selectedName || "—"))}
      </div>
      <div className="mb-3 text-xs text-slate-500">
        <span className="font-medium text-slate-600">Fuente: </span>
        {custom
          ? "Valores definidos por el usuario"
          : (matched?.source ?? "—")}
      </div>

      {showChart ? (
        <div className="h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 6, right: 8, left: 0, bottom: 0 }}
              onClick={
                editing
                  ? (state: { activeTooltipIndex?: number }) => {
                      const idx = state?.activeTooltipIndex;
                      if (typeof idx === "number") setFocusYear(idx + 1);
                    }
                  : undefined
              }
            >
              <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
              <XAxis
                dataKey="year"
                tick={AXIS}
                stroke={C.slate}
                interval={4}
                label={{
                  value: "Año",
                  position: "insideBottomRight",
                  offset: -2,
                  fontSize: 10,
                  fill: "#94a3b8",
                }}
              />
              <YAxis
                tick={AXIS}
                stroke={C.slate}
                width={44}
                label={
                  unit
                    ? {
                        value: unit,
                        angle: -90,
                        position: "insideLeft",
                        fontSize: 10,
                        fill: "#94a3b8",
                      }
                    : undefined
                }
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v: number) => [`${v}${unit ? ` ${unit}` : ""}`, "Precio"]}
                labelFormatter={(l) => `Año ${l}`}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={C.accent}
                dot={editing ? renderDot : false}
                activeDot={
                  editing
                    ? { r: 5, fill: C.accent, cursor: "ns-resize" }
                    : { r: 4 }
                }
                strokeWidth={2}
                isAnimationActive={!editing}
                animationDuration={editing ? 0 : 600}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="grid h-40 place-items-center text-xs text-slate-400">
          Sin datos de curva.
        </div>
      )}

      {editing && (
        <div ref={editPanelRef} className="mt-3 space-y-3">
          {/* Quick helpers */}
          <div className="flex flex-wrap items-end gap-2 rounded-md border border-slate-200 bg-slate-50 p-2">
            <div className="flex flex-col">
              <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
                Valor base (Año 1)
              </label>
              <input
                aria-label="Valor base año 1"
                type="number"
                step="any"
                value={base}
                onChange={(e) => setBase(e.target.value)}
                className="w-24 rounded border border-slate-300 px-2 py-1 text-right text-xs tabular-nums focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </div>
            <button
              type="button"
              onClick={setBaseYearOne}
              className="rounded border border-slate-300 px-2 py-1 text-[11px] text-slate-600 transition hover:bg-white"
            >
              Fijar Año 1
            </button>
            <div className="flex flex-col">
              <label className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
                % anual
              </label>
              <input
                aria-label="Crecimiento anual en porcentaje"
                type="number"
                step="any"
                value={pct}
                onChange={(e) => setPct(e.target.value)}
                placeholder="p.ej. -2"
                className="w-24 rounded border border-slate-300 px-2 py-1 text-right text-xs tabular-nums focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </div>
            <button
              type="button"
              onClick={applyGrowth}
              className="rounded border border-slate-300 px-2 py-1 text-[11px] text-slate-600 transition hover:bg-white"
            >
              Aplicar crecimiento
            </button>
          </div>

          {/* Year-by-year editable grid */}
          <div
            ref={gridRef}
            className="max-h-44 overflow-y-auto rounded-md border border-slate-200 p-2"
          >
            <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
              {working.map((v, i) => (
                <label
                  key={i}
                  className={`flex items-center gap-1 rounded px-1 py-0.5 ${
                    focusYear === i + 1 ? "bg-accent-50 ring-1 ring-accent-200" : ""
                  }`}
                >
                  <span className="w-9 shrink-0 text-right text-[10px] tabular-nums text-slate-400">
                    A{i + 1}
                  </span>
                  <input
                    ref={(el) => {
                      cellRefs.current[i] = el;
                    }}
                    aria-label={`Año ${i + 1}`}
                    type="number"
                    step="any"
                    value={Number.isFinite(v) ? v : 0}
                    onFocus={() => setFocusYear(i + 1)}
                    onChange={(e) => setCell(i, e.target.valueAsNumber)}
                    className="w-full min-w-0 rounded border border-slate-200 px-1 py-0.5 text-right text-xs tabular-nums focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-slate-400">
              Arrastra un punto del gráfico para ajustar ese año, o púlsalo para
              editarlo en la cuadrícula.
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={restore}
                className="rounded px-2.5 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100"
              >
                Restaurar
              </button>
              <button
                type="button"
                onClick={apply}
                className="rounded bg-accent-600 px-3 py-1 text-[11px] font-medium text-white transition hover:bg-accent-700"
              >
                Aplicar
              </button>
            </div>
          </div>
        </div>
      )}

      {custom && !editing && editable && (
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={restore}
            className="rounded px-2.5 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100"
          >
            Restaurar curva de librería
          </button>
        </div>
      )}
    </div>
  );
}
