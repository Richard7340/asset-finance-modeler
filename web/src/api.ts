const BASE = import.meta.env.VITE_API_BASE ?? "";
const params = new URLSearchParams(location.search);
const token = params.get("t") ?? "";
export const isEmbed = params.get("embed") === "1";

/** Append the auth token query, preserving an existing query string. */
function withToken(path: string): string {
  if (!token) return `${BASE}${path}`;
  const sep = path.includes("?") ? "&" : "?";
  return `${BASE}${path}${sep}t=${token}`;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AssetType =
  | "solar"
  | "bess"
  | "wind"
  | "datacenter"
  | "hybrid_consolidated"
  | "hybrid"
  | "business"
  | "real_estate";

export type ModelSummary = {
  id: string;
  name: string;
  asset_type: AssetType;
};

export type InputType = "number" | "bool" | "text";

export type SchemaInput = {
  path: string;
  value: number | string | boolean;
  type: InputType;
  section: string;
  label: string;
};

export type ModelSchema = { inputs: SchemaInput[] };

export type Kpis = Record<string, number>;

export type IncomeStatement = {
  years: number[];
  rows: {
    revenue: number[];
    ebitda: number[];
    ebit: number[];
    interest_expense: number[];
    ebt: number[];
    tax: number[];
    net_income: number[];
  };
};

export type CashFlow = {
  years: number[];
  cfo: number[];
  cfi: number[];
  cff: number[];
};

/** Generic infra/business run result. */
export type GenericResult = {
  kpis: Kpis;
  income_statement: IncomeStatement;
  cash_flow: CashFlow;
  summary?: Record<string, unknown>;
};

/** Legacy hybrid_consolidated v1 result shape. */
export type HybridResult = {
  kpis: Kpis;
  cashflows: { years: number[]; fv: number[]; bess: number[] };
  curves: { spread: number[]; ancillary: number[] };
  bridge: { fv: number; bess: number; hybrid: number };
  dscr_profile: number[];
};

export type RunResult = Partial<GenericResult> & Partial<HybridResult>;

/** Discriminate the two backend response shapes defensively. */
export function isGenericResult(r: RunResult): r is GenericResult {
  return !!r.income_statement;
}
export function isHybridResult(r: RunResult): r is HybridResult {
  return !r.income_statement && !!r.cashflows;
}

/**
 * Override values can be:
 *  - number  → a scalar input
 *  - string  → a curve selector (e.g. `spread_curve_name` = "spread_da_es")
 *             or a free-text/enum input
 *  - boolean → a flag input (e.g. `taxes.enabled`)
 *  - number[] → a custom curve supplied by the user (e.g. `spread_points`)
 */
export type OverrideValue = number | string | boolean | number[];
export type Overrides = Record<string, OverrideValue>;

// ---------------------------------------------------------------------------
// Price curves (consultant catalogue) — TDD transparency surface
// ---------------------------------------------------------------------------

export type Curve = {
  name: string;
  /** Consultant citation, e.g. "Agere TB2 España + Modo Energy". */
  source: string;
  /** Parameter the curve drives, e.g. "spread_eur_mwh". */
  parameter: string;
  asset_type: string;
  bankable: boolean;
  /** 30-year yearly values. */
  values: number[];
};

export async function getCurves(parameter?: string): Promise<{ curves: Curve[] }> {
  const q = parameter ? `?parameter=${encodeURIComponent(parameter)}` : "";
  return getJson<{ curves: Curve[] }>(`/api/curves${q}`);
}

export async function getCurve(name: string): Promise<Curve> {
  return getJson<Curve>(`/api/curves/${encodeURIComponent(name)}`);
}

export type Lifecycle = "opportunity" | "operational";
export type TrackingFrequency = "daily" | "monthly" | "quarterly";

/** Optional free-text location + coordinates for the portfolio map (F4-2). */
export type AssetLocation = {
  location?: string | null;
  lat?: number | null;
  lon?: number | null;
};

export type SavedAssetSummary = {
  id: string;
  name: string;
  model_id: string;
  created_at: string;
  /** Most-recent-activity timestamp (latest actual's entered_at, else created_at). */
  last_update: string;
  kpis: Kpis;
  lifecycle: Lifecycle;
  commissioning_date: string | null;
  tracking_frequency: TrackingFrequency | null;
} & AssetLocation;

export type SavedAsset = {
  id: string;
  name: string;
  model_id: string;
  overrides: Overrides;
  results_snapshot: RunResult | null;
  created_at: string;
} & AssetLocation;

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(withToken(path));
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export async function listModels(): Promise<ModelSummary[]> {
  const d = await getJson<{ models: ModelSummary[] }>("/api/models");
  return d.models;
}

export async function getSchema(modelId: string): Promise<ModelSchema> {
  return getJson<ModelSchema>(`/api/models/${modelId}/schema`);
}

export async function runModel(
  modelId: string,
  overrides: Overrides,
): Promise<RunResult> {
  const r = await fetch(withToken(`/api/models/${modelId}/run`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  if (!r.ok) throw new Error(`run failed: ${r.status}`);
  return r.json();
}

/**
 * Excel export. Only the legacy hybrid_consolidated endpoint exists in the backend, so export
 * is only available for the hybrid_consolidated model. Returns false if the model is
 * not exportable.
 */
export function canExport(modelId: string): boolean {
  return modelId === "hybrid_consolidated";
}

export async function downloadExcel(
  modelId: string,
  overrides: Overrides,
): Promise<void> {
  if (!canExport(modelId)) {
    throw new Error("Este modelo no admite exportación a Excel todavía.");
  }
  const r = await fetch(withToken(`/api/hybrid_consolidated/export`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  if (!r.ok) throw new Error(`export failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${modelId}_simulacion.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Persistence (Mi cartera)
// ---------------------------------------------------------------------------

export async function listAssets(lifecycle?: Lifecycle): Promise<SavedAssetSummary[]> {
  const q = lifecycle ? `?lifecycle=${lifecycle}` : "";
  const d = await getJson<{ assets: SavedAssetSummary[] }>(`/api/assets${q}`);
  return d.assets;
}

export async function getAsset(id: string): Promise<SavedAsset> {
  return getJson<SavedAsset>(`/api/assets/${id}`);
}

export async function saveAsset(
  modelId: string,
  name: string,
  overrides: Overrides,
  location?: AssetLocation,
): Promise<{ id: string }> {
  const r = await fetch(withToken("/api/assets"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId, name, overrides, ...(location ?? {}) }),
  });
  if (!r.ok) throw new Error(`save failed: ${r.status}`);
  return r.json();
}

export async function deleteAsset(id: string): Promise<void> {
  const r = await fetch(withToken(`/api/assets/${id}`), { method: "DELETE" });
  if (!r.ok) throw new Error(`delete failed: ${r.status}`);
}

export async function setLifecycle(
  id: string,
  body: { lifecycle: Lifecycle; tracking_frequency?: TrackingFrequency; commissioning_date?: string },
): Promise<{ id: string; lifecycle: Lifecycle; base_locked: boolean; commissioning_date: string | null; tracking_frequency: TrackingFrequency | null }> {
  const r = await fetch(withToken(`/api/assets/${id}/lifecycle`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`lifecycle update failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Datos reales (actuals) + varianza real-vs-base (F2)
// ---------------------------------------------------------------------------

/** A model line that can receive real data (e.g. revenue, ebitda, cfo). */
export type TrackableLine = {
  path: string;
  label: string;
  /** Unit hint from the backend; may be "". */
  unit: string;
};

/** A single real-data point entered for a line at a period. */
export type Actual = {
  id: string;
  period_start: string;
  line_path: string;
  value: number;
  unit: string;
  note: string;
  entered_by: string;
  entered_at: string;
};

/** An actual to create (subset the POST body accepts). */
export type ActualInput = {
  period_start: string;
  line_path: string;
  value: number;
  unit?: string;
  note?: string;
};

/** Per-line variance series: frozen base vs aggregated actuals by model year. */
export type VarianceLine = {
  line_path: string;
  label: string;
  unit: string;
  /** Frozen base series (annual), one value per model year. */
  base: number[];
  /** Real series aggregated by year; null where no actual was entered. */
  actual: (number | null)[];
  /** Absolute deviation (actual - base) per year; null where no actual. */
  deviation: (number | null)[];
  /** Relative deviation (decimal); null where no actual or base is 0. */
  deviation_pct: (number | null)[];
  /** Sum of actuals over the years that have data. */
  cumulative_actual: number;
  /** Sum of base over the same years (so partial series are fair). */
  cumulative_base: number;
  /** cumulative_actual / cumulative_base (decimal); null if no data. */
  fulfillment_pct: number | null;
};

export type Variance = { lines: VarianceLine[] };

export async function getLines(id: string): Promise<TrackableLine[]> {
  const d = await getJson<{ lines: TrackableLine[] }>(`/api/assets/${id}/lines`);
  return d.lines;
}

export async function getActuals(
  id: string,
  opts?: { linePath?: string; since?: string; until?: string },
): Promise<Actual[]> {
  const qs: string[] = [];
  if (opts?.linePath) qs.push(`line_path=${encodeURIComponent(opts.linePath)}`);
  if (opts?.since) qs.push(`since=${encodeURIComponent(opts.since)}`);
  if (opts?.until) qs.push(`until=${encodeURIComponent(opts.until)}`);
  const q = qs.length ? `?${qs.join("&")}` : "";
  const d = await getJson<{ actuals: Actual[] }>(`/api/assets/${id}/actuals${q}`);
  return d.actuals;
}

export async function postActuals(
  id: string,
  actuals: ActualInput[],
): Promise<{ ids: string[] }> {
  const r = await fetch(withToken(`/api/assets/${id}/actuals`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actuals }),
  });
  if (!r.ok) throw new Error(`postActuals failed: ${r.status}`);
  return r.json();
}

export async function deleteActual(id: string, actualId: string): Promise<void> {
  const r = await fetch(withToken(`/api/assets/${id}/actuals/${actualId}`), {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`deleteActual failed: ${r.status}`);
}

export async function getVariance(id: string, linePath?: string): Promise<Variance> {
  const q = linePath ? `?line_path=${encodeURIComponent(linePath)}` : "";
  return getJson<Variance>(`/api/assets/${id}/variance${q}`);
}

// ---------------------------------------------------------------------------
// Reproyección viva (LIVE) — base congelado vs live (reales + reproyección) (F3)
// ---------------------------------------------------------------------------

/** KPIs for one scenario (base or live). */
export type LiveKpis = {
  npv: number;
  irr_project: number;
  dscr_min: number;
  dscr_avg: number;
};

/** One scenario's full output (base or live). */
export type LiveScenario = {
  kpis: LiveKpis;
  income_statement: IncomeStatement;
  cash_flow: CashFlow;
};

/** Head-to-head comparison between base and live. */
export type LiveComparison = {
  npv_base: number;
  npv_live: number;
  /** npv_live - npv_base. */
  delta: number;
  irr_base: number;
  irr_live: number;
  dscr_min_base: number;
  dscr_min_live: number;
  /** Whole years elapsed since commissioning. */
  elapsed_years: number;
  /** Total model years. */
  n_years: number;
};

export type LiveResult = {
  base: LiveScenario;
  live: LiveScenario;
  comparison: LiveComparison;
};

/**
 * Base-vs-live reprojection for an operational asset. Throws on 422 for a
 * non-operational asset (the caller gates on lifecycle, so this is defensive).
 */
export async function getLive(id: string): Promise<LiveResult> {
  return getJson<LiveResult>(`/api/assets/${id}/live`);
}

// ---------------------------------------------------------------------------
// Portfolio (Cartera) — aggregate view
// ---------------------------------------------------------------------------

export type PortfolioAsset = {
  id: string;
  name: string;
  model_id: string;
  npv: number;
  revenue_y1: number;
  capex: number;
  /** Internal rate of return, decimal (e.g. 0.06 = 6%). */
  irr: number;
  /** Yield = VAN / CAPEX, decimal. */
  yield_pct: number;
} & AssetLocation;

export type PortfolioTotals = {
  npv: number;
  capex: number;
  revenue_y1: number;
  count: number;
  /** CAPEX-weighted IRR across included assets, decimal. */
  irr_weighted?: number;
};

export type Portfolio = {
  assets: PortfolioAsset[];
  totals: PortfolioTotals;
};

export async function getPortfolio(
  opts?: { ids?: string[]; lifecycle?: Lifecycle },
): Promise<Portfolio> {
  const qs: string[] = [];
  if (opts?.ids && opts.ids.length > 0)
    qs.push(`ids=${opts.ids.map(encodeURIComponent).join(",")}`);
  if (opts?.lifecycle) qs.push(`lifecycle=${opts.lifecycle}`);
  const q = qs.length ? `?${qs.join("&")}` : "";
  return getJson<Portfolio>(`/api/portfolio${q}`);
}
