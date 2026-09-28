import { useState } from "react";
import type React from "react";
import { BarChart3, CalendarRange, Coins, Landmark, LayoutDashboard, Table2 } from "lucide-react";
import type { RunResult, TrackingFrequency } from "../../api";
import KpiCards from "../KpiCards";
import Charts from "../Charts";
import IncomeStatementTable from "../IncomeStatement";
import CashFlowTable from "../CashFlowTable";
import ActualsGrid from "../ActualsGrid";
import VariancePanel from "../VariancePanel";
import LivePanel from "../LivePanel";
import { AssetAlerts } from "../Alerts";
import DeudaPanel, { Dato } from "./DeudaPanel";
import ValoracionPanel from "./ValoracionPanel";
import SerieRealPanel from "./SerieRealPanel";
import { eur, mult } from "../../format";

type Pestana = "resumen" | "real" | "curvas" | "deuda" | "valor" | "estados";

/**
 * La ficha de un activo por pestañas (28-sep), como la leería un gestor:
 * Resumen · Real vs previsto (si está en marcha) · Curvas · Deuda · Valoración ·
 * Estados financieros. `curvas` es el editor de curvas de precios del modelo.
 */
export default function Ficha({
  result, hybrid, assetId, operativo, trackingFrequency, curvas, pie,
}: {
  result: RunResult;
  hybrid: boolean;
  assetId: string | null;
  operativo: boolean;
  trackingFrequency: TrackingFrequency | null;
  curvas?: React.ReactNode;
  pie?: React.ReactNode;
}) {
  const deuda = (result as { deuda?: import("../../api").Deuda }).deuda;
  const hayDeuda = !!deuda && deuda.disposiciones.some((x) => x > 0);
  const pestanas: Array<[Pestana, string, React.ComponentType<{ size?: number; strokeWidth?: number }>]> = [
    ["resumen", "Resumen", LayoutDashboard],
    ...(operativo && assetId ? ([["real", "Real vs previsto", CalendarRange]] as Array<[Pestana, string, typeof CalendarRange]>) : []),
    ["curvas", "Curvas y resultados", BarChart3],
    ...(hayDeuda ? ([["deuda", "Deuda", Landmark]] as Array<[Pestana, string, typeof Landmark]>) : []),
    ...(assetId && !hybrid ? ([["valor", "Valoración", Coins]] as Array<[Pestana, string, typeof Coins]>) : []),
    ...(!hybrid ? ([["estados", "Estados financieros", Table2]] as Array<[Pestana, string, typeof Table2]>) : []),
  ];
  const [p, setP] = useState<Pestana>(operativo && assetId ? "real" : "resumen");
  const actual = pestanas.some(([k]) => k === p) ? p : "resumen";
  const k = result.kpis ?? {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-0">
        {pestanas.map(([id, nombre, Icono]) => (
          <button
            key={id}
            type="button"
            onClick={() => setP(id)}
            className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition ${
              actual === id ? "border-accent-500 text-accent-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Icono size={14} strokeWidth={2} />
            {nombre}
          </button>
        ))}
      </div>

      {actual === "resumen" && (
        <div className="space-y-4">
          <KpiCards data={result} />
          {!hybrid && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {k.payback_years != null && <Dato label="Recuperas la inversión" valor={`${k.payback_years.toLocaleString("es-ES")} años`} />}
              {k.dscr_avg != null && <Dato label="DSCR medio" valor={mult(k.dscr_avg)} tono={k.dscr_avg >= 1.3 ? "bien" : k.dscr_avg >= 1.1 ? "justo" : "mal"} />}
              {k.lcoe != null && <Dato label="Coste de la energía (LCOE)" valor={`${k.lcoe.toLocaleString("es-ES")} €/MWh`} />}
              {hayDeuda && <Dato label="Deuda pedida" valor={eur(deuda!.disposiciones.reduce((a, b) => a + b, 0))} />}
            </div>
          )}
          {assetId && operativo && <AssetAlerts assetId={assetId} />}
          <Charts data={result} />
        </div>
      )}

      {actual === "real" && assetId && (
        <div className="space-y-4">
          <AssetAlerts assetId={assetId} />
          <SerieRealPanel assetId={assetId} />
          <ActualsGrid assetId={assetId} trackingFrequency={trackingFrequency} />
          <VariancePanel assetId={assetId} />
          <LivePanel assetId={assetId} />
          {pie}
        </div>
      )}

      {actual === "curvas" && (
        <div className="space-y-4">
          <Charts data={result} />
          {curvas}
        </div>
      )}

      {actual === "deuda" && deuda && <DeudaPanel deuda={deuda} />}

      {actual === "valor" && assetId && <ValoracionPanel assetId={assetId} />}

      {actual === "estados" && !hybrid && (
        <div className="space-y-4">
          {result.income_statement && <IncomeStatementTable data={result.income_statement} />}
          {result.cash_flow && <CashFlowTable data={result.cash_flow} />}
        </div>
      )}
    </div>
  );
}
