import { useEffect, useState } from "react";

/** Theme-aware colors for recharts (axes, grid, tooltip), which take inline
 * style/props and cannot use Tailwind `dark:` variants. */
export type ChartTheme = {
  dark: boolean;
  grid: string;
  axis: string;
  axisStroke: string;
  zeroLine: string;
  /** Stroke between donut slices / chart surface background accents. */
  sliceStroke: string;
  tooltip: React.CSSProperties;
};

const LIGHT: ChartTheme = {
  dark: false,
  grid: "#eef2f7",
  axis: "#64748b",
  axisStroke: "#94a3b8",
  zeroLine: "#cbd5e1",
  sliceStroke: "#ffffff",
  tooltip: {
    fontSize: 12,
    borderRadius: 10,
    border: "1px solid #e2e8f0",
    boxShadow: "0 6px 24px rgb(15 23 42 / 0.10)",
    padding: "8px 10px",
    background: "#ffffff",
    color: "#0f172a",
  },
};

const DARK: ChartTheme = {
  dark: true,
  grid: "#1e293b",
  axis: "#94a3b8",
  axisStroke: "#475569",
  zeroLine: "#334155",
  sliceStroke: "#0b1220",
  tooltip: {
    fontSize: 12,
    borderRadius: 10,
    border: "1px solid #1e293b",
    boxShadow: "0 6px 24px rgb(0 0 0 / 0.5)",
    padding: "8px 10px",
    background: "#111a2e",
    color: "#e2e8f0",
  },
};

function isDark(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

/** Observe the `dark` class on <html> and return theme-aware chart colors. */
export function useChartTheme(): ChartTheme {
  const [dark, setDark] = useState<boolean>(isDark);

  useEffect(() => {
    if (typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(() => setDark(isDark()));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    setDark(isDark());
    return () => obs.disconnect();
  }, []);

  return dark ? DARK : LIGHT;
}
