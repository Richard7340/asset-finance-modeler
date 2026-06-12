import type { IncomeStatement as IS } from "../api";
import { eurExact } from "../format";

const ROWS: { key: keyof IS["rows"]; label: string; bold?: boolean }[] = [
  { key: "revenue", label: "Ingresos", bold: true },
  { key: "ebitda", label: "EBITDA", bold: true },
  { key: "ebit", label: "EBIT" },
  { key: "interest_expense", label: "Gastos financieros" },
  { key: "ebt", label: "BAI" },
  { key: "tax", label: "Impuestos" },
  { key: "net_income", label: "Beneficio neto", bold: true },
];

export default function IncomeStatement({ data }: { data: IS }) {
  const { years, rows } = data;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        Cuenta de resultados
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
              const series = rows[r.key] ?? [];
              return (
                <tr
                  key={r.key}
                  className={`border-b border-slate-50 ${
                    r.bold ? "font-semibold text-slate-800" : "text-slate-600"
                  }`}
                >
                  <td className="sticky left-0 z-10 bg-white py-1.5 pr-3 text-left">
                    {r.label}
                  </td>
                  {series.map((v, i) => (
                    <td
                      key={i}
                      className={`px-2 py-1.5 text-right ${
                        v < 0 ? "text-rose-600" : ""
                      }`}
                    >
                      {eurExact(v)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
