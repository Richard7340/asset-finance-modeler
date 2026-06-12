import type { CashFlow } from "../api";
import { eurExact } from "../format";
import Reveal from "./Reveal";

const ROWS: { key: keyof Omit<CashFlow, "years">; label: string }[] = [
  { key: "cfo", label: "Flujo de operaciones (CFO)" },
  { key: "cfi", label: "Flujo de inversión (CFI)" },
  { key: "cff", label: "Flujo de financiación (CFF)" },
];

export default function CashFlowTable({ data }: { data: CashFlow }) {
  const { years, cfo, cfi } = data;

  return (
    <Reveal className="surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">
        Flujos de caja
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs tabular-nums">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="sticky left-0 z-10 bg-white py-1.5 pr-3 text-left font-medium">
                €
              </th>
              {years.map((y) => (
                <th key={y} className="px-2 py-1.5 text-right font-medium">
                  Año {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => {
              const series = data[r.key] ?? [];
              return (
                <tr
                  key={r.key}
                  className="border-b border-slate-50 text-slate-600 transition hover:bg-slate-50/70"
                >
                  <td className="sticky left-0 z-10 bg-white py-1.5 pr-3 text-left">
                    {r.label}
                  </td>
                  {series.map((v, i) => (
                    <td
                      key={i}
                      className={`px-2 py-1.5 text-right ${v < 0 ? "text-rose-600" : ""}`}
                    >
                      {eurExact(v)}
                    </td>
                  ))}
                </tr>
              );
            })}
            <tr className="border-b border-slate-100 font-semibold text-slate-900">
              <td className="sticky left-0 z-10 bg-white py-1.5 pr-3 text-left">
                FCF (CFO+CFI)
              </td>
              {years.map((_, i) => {
                const v = (cfo[i] ?? 0) + (cfi[i] ?? 0);
                return (
                  <td
                    key={i}
                    className={`px-2 py-1.5 text-right ${v < 0 ? "text-rose-600" : ""}`}
                  >
                    {eurExact(v)}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </Reveal>
  );
}
