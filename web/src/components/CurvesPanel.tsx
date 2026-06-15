import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
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
import type { Curve, ModelSchema, Overrides, SchemaInput } from "../api";

type Props = {
  schema: ModelSchema;
  overrides: Overrides;
};

const CURVE_NAME_SUFFIX = "curve_name";

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
 * "Curvas de mercado y fuentes" — for every curve-driven input in the current
 * model, shows the selected curve, its consultant source, a 30-year chart and a
 * bankability tag. This is the TDD-transparency surface for an advisory review.
 */
export default function CurvesPanel({ schema, overrides }: Props) {
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
        Curvas de consultor que alimentan las proyecciones. Fuente y horizonte
        explícitos para revisión (TDD).
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
}: {
  inp: SchemaInput;
  matched: Curve | undefined;
  custom: boolean;
  customPoints: number[] | undefined;
  selectedName: string;
}) {
  const chartData = custom
    ? (customPoints ?? []).map((v, i) => ({ year: i + 1, value: v }))
    : (matched?.values ?? []).map((v, i) => ({ year: i + 1, value: v }));
  const showChart = chartData.length > 0;

  return (
    <div className="surface-hover rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div
            className="truncate text-sm font-semibold text-slate-800"
            title={inp.path}
          >
            {fieldLabel(inp)}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">
            {matched?.parameter ?? inp.path.split(".").slice(-2)[0]}
          </div>
        </div>
        {!custom && matched && (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              matched.bankable
                ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
            }`}
          >
            {matched.bankable ? "Bankable" : "No bankable"}
          </span>
        )}
      </div>

      <div className="mb-1 text-sm font-medium text-slate-900">
        {custom ? "Curva propia" : (matched?.name ?? (selectedName || "—"))}
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
            <LineChart data={chartData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
              <XAxis dataKey="year" tick={AXIS} stroke={C.slate} interval={4} />
              <YAxis tick={AXIS} stroke={C.slate} width={44} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line
                type="monotone"
                dataKey="value"
                stroke={C.accent}
                dot={false}
                strokeWidth={2}
                animationDuration={800}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="grid h-40 place-items-center text-xs text-slate-400">
          Sin datos de curva.
        </div>
      )}
    </div>
  );
}
