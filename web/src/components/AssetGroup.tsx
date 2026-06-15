import type { ReactNode } from "react";

type Props = {
  title: string;
  subtitle: string;
  icon: ReactNode;
  count: number;
  children: ReactNode;
};

export default function AssetGroup({ title, subtitle, icon, count, children }: Props) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 border-b border-slate-200 pb-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-600/10 text-accent-700">
          {icon}
        </span>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold tabular-nums text-slate-700">
          {count}
        </span>
      </div>
      {children}
    </section>
  );
}
