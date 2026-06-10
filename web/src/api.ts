const BASE = import.meta.env.VITE_API_BASE ?? "";
const params = new URLSearchParams(location.search);
const token = params.get("t") ?? "";
export const isEmbed = params.get("embed") === "1";
const q = token ? `?t=${token}` : "";

export type ModelInput = {
  key: string;
  label: string;
  unit: string;
  default: number;
  min: number;
  max: number;
};

export type Model = { name: string; inputs: ModelInput[] };

export type RunResult = {
  kpis: Record<string, number>;
  cashflows: { years: number[]; fv: number[]; bess: number[] };
  curves: { spread: number[]; ancillary: number[] };
  bridge: { fv: number; bess: number; hybrid: number };
  dscr_profile: number[];
};

export async function getModel(): Promise<Model> {
  const r = await fetch(`${BASE}/api/svj/model${q}`);
  if (!r.ok) throw new Error(`getModel failed: ${r.status}`);
  return r.json();
}

export async function runModel(
  overrides: Record<string, number>,
): Promise<RunResult> {
  const r = await fetch(`${BASE}/api/svj/run${q}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  if (!r.ok) throw new Error(`runModel failed: ${r.status}`);
  return r.json();
}

export async function downloadExcel(overrides: Record<string, number>) {
  const r = await fetch(`${BASE}/api/svj/export${q}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  if (!r.ok) throw new Error(`export failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "SVJ_simulacion.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
