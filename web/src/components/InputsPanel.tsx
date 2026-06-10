import type { Model } from "../api";

export default function InputsPanel({
  model,
  overrides,
  onChange,
}: {
  model: Model;
  overrides: Record<string, number>;
  onChange: (key: string, value: number) => void;
}) {
  return (
    <div className="space-y-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Parámetros
      </h2>
      {model.inputs.map((inp) => {
        const value = overrides[inp.key] ?? inp.default;
        const step = (inp.max - inp.min) / 100 || 0.01;
        return (
          <div key={inp.key} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2">
              <label className="text-sm font-medium text-slate-700">
                {inp.label}
              </label>
              <span className="text-xs text-slate-400">{inp.unit}</span>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={inp.min}
                max={inp.max}
                step={step}
                value={value}
                onChange={(e) => onChange(inp.key, Number(e.target.value))}
                className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-slate-200 accent-indigo-600"
              />
              <input
                type="number"
                min={inp.min}
                max={inp.max}
                step={step}
                value={value}
                onChange={(e) => onChange(inp.key, Number(e.target.value))}
                className="w-24 rounded-md border border-slate-300 px-2 py-1 text-right text-sm tabular-nums focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
