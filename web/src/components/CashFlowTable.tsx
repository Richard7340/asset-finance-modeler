import {
  Bar,
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CashFlow } from "../api";
import { eur, eurExact } from "../format";

const ROWS: { key: keyof Omit<CashFlow, "years">; label: string }[] = [
  { key: "cfo", label: "Flujo de operaciones (CFO)" },
  { key: "cfi", label: "Flujo de inversión (CFI)" },
  { key: "cff", label: "Flujo de financiación (CFF)" },
];

export default function CashFlowTable({ data }: { data: CashFlow }) {
  const { years, cfo, cfi, cff } = data;

  const chartData = years.map((y, i) => ({
    year: `A${y}`,
    cfo: cfo[i] ?? 0,
    cfi: cfi[i] ?? 0,
    cff: cff[i] ?? 0,
    fcf: (cfo[i] ?? 0) + (cfi[i] ?? 0),
  }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        Flujos de caja
      </h3>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#64748b" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={(v) => eur(Number(v))}
              width={70}
            />
            <Tooltip
              formatter={(v: number) => eur(Number(v))}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="cfo" name="CFO" fill="#0ea5e9" />
            <Bar dataKey="cfi" name="CFI" fill="#94a3b8" />
            <Bar dataKey="cff" name="CFF" fill="#cbd5e1" />
            <Line
              type="monotone"
              dataKey="fcf"
              name="FCF (CFO+CFI)"
              stroke="#0f172a"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 overflow-x-auto">
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
                <tr key={r.key} className="border-b border-slate-50 text-slate-600">
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
            <tr className="border-b border-slate-100 font-semibold text-slate-800">
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
    </div>
  );
}
