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
  | "svj"
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
  /** Calendario de la deuda año a año (28-sep). */
  deuda?: Deuda;
};

/** Legacy svj_hybrid v1 result shape. */
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
 * Excel export. Only the legacy svj endpoint exists in the backend, so export
 * is only available for the svj_hybrid model. Returns false if the model is
 * not exportable.
 */
export function canExport(modelId: string): boolean {
  return modelId === "svj_hybrid";
}

export async function downloadExcel(
  modelId: string,
  overrides: Overrides,
): Promise<void> {
  if (!canExport(modelId)) {
    throw new Error("Este modelo no admite exportación a Excel todavía.");
  }
  const r = await fetch(withToken(`/api/svj/export`), {
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
  /** La previsión con la que se compara cada año (el año en curso, solo hasta hoy). */
  base_comparada?: (number | null)[];
  /** Índice del año en curso (0 = primer año del modelo), o null si está fuera. */
  anio_en_curso?: number | null;
  /** Parte del año en curso ya transcurrida (0-1). */
  fraccion_del_anio?: number | null;
  /** Mes a mes del año en curso: lo real frente a la previsión mensual. */
  mensual?: { mes: number; real: number | null; prevision: number }[] | null;
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
  /** Tipo de activo (28-sep). */
  tipo?: TipoDeActivo;
  lifecycle?: Lifecycle | null;
  anio_inicio?: number;
  enterprise_value?: number | null;
  valor_para_el_dueno?: number | null;
  /** Deuda viva, caja, ingresos y EBITDA del año en curso. */
  deuda_viva?: number | null;
  caja?: number | null;
  ingresos_anio?: number | null;
  ebitda_anio?: number | null;
  /** Series anuales del modelo (año 1, 2, …). */
  series?: { revenue: number[]; ebitda: number[]; net_income: number[]; flujo_caja: number[]; deuda: number[] };
  /** El año en curso: lo real hasta hoy frente a lo previsto hasta hoy. */
  ytd?: { real: number; prevision: number };
} & AssetLocation;

export type TipoDeActivo = "negocio" | "inmueble" | "renovable" | "infraestructura" | "saas";

export type PortfolioTotals = {
  npv: number;
  capex: number;
  revenue_y1: number;
  count: number;
  /** CAPEX-weighted IRR across included assets, decimal. */
  irr_weighted?: number;
  enterprise_value?: number;
  valor_para_el_dueno?: number;
  deuda_viva?: number;
  caja?: number;
  ingresos_anio?: number;
  ebitda_anio?: number;
  /** Real / previsto del año en curso (activos con datos reales), en %. */
  cumplimiento_ytd_pct?: number;
  ytd?: { real: number; prevision: number };
};

/** Series de toda la cartera por AÑO NATURAL. */
export type Consolidado = {
  years: number[];
  revenue: number[];
  ebitda: number[];
  net_income: number[];
  flujo_caja: number[];
  deuda: number[];
};

export type Portfolio = {
  assets: PortfolioAsset[];
  totals: PortfolioTotals;
  consolidado?: Consolidado;
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


// ---------------------------------------------------------------------------
// Ficha del activo (28-sep): deuda, valoración y real por frecuencia.
// ---------------------------------------------------------------------------

export type Deuda = {
  years: number[];
  saldo: number[];
  intereses: number[];
  amortizacion: number[];
  disposiciones: number[];
  dscr: Array<number | null>;
};

export type Valoracion = {
  activo?: string;
  metodo?: string;
  tasa_descuento: number;
  crecimiento_final: number;
  anios: number;
  flujos_libres: number[];
  dcf: { vp_flujos: number; valor_terminal: number; vp_valor_terminal: number; valor_empresa: number };
  peso_valor_terminal: number;
  deuda_neta: number;
  valor_empresa: number;
  valor_para_el_dueno: number;
  inversion_inicial?: number;
  van?: number;
  ev_ebitda_implicito?: number | null;
  multiplo?: { ebitda_referencia: number; multiplo: number; valor_empresa?: number } | null;
  rango_valor_empresa?: [number, number];
  rango_para_el_dueno?: [number, number];
  sensibilidad?: { tasas: number[]; crecimientos: number[]; valor_empresa: number[][] };
  notas?: string[];
};

export async function getValoracion(
  id: string,
  opts?: { tasa?: number; crecimiento?: number; deuda_neta?: number; multiplo_ebitda?: number },
): Promise<Valoracion> {
  const qs = Object.entries(opts ?? {})
    .filter(([, v]) => v !== undefined && Number.isFinite(v))
    .map(([k, v]) => `${k}=${v}`);
  return getJson<Valoracion>(`/api/assets/${encodeURIComponent(id)}/valoracion${qs.length ? "?" + qs.join("&") : ""}`);
}

export type Cada = "dia" | "semana" | "mes" | "anio";

export type SerieReal = {
  line_path: string;
  cada: Cada;
  desde: string;
  hasta: string;
  puntos: Array<{
    desde: string;
    etiqueta: string;
    real: number | null;
    prevision: number;
    acumulado_real: number;
    acumulado_prevision: number;
    desviacion_pct: number | null;
  }>;
  resumen: { real: number | null; prevision_de_esos_periodos: number; cumplimiento_pct: number | null; periodos_con_dato: number };
  /** De dónde sale el reparto mensual de la previsión. */
  estacionalidad?: string;
};

export async function getSerie(id: string, linePath: string, cada: Cada, desde?: string, hasta?: string): Promise<SerieReal> {
  const qs = [`line_path=${encodeURIComponent(linePath)}`, `cada=${cada}`];
  if (desde) qs.push(`desde=${desde}`);
  if (hasta) qs.push(`hasta=${hasta}`);
  return getJson<SerieReal>(`/api/assets/${encodeURIComponent(id)}/serie?${qs.join("&")}`);
}
