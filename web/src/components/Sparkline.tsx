import { useId } from "react";

type Props = {
  /** Series to plot; needs at least 2 finite points to render. */
  values: number[];
  /** Stroke color (defaults to the indigo accent). */
  color?: string;
  width?: number;
  height?: number;
  /** Fill a faint area under the line. */
  fill?: boolean;
  className?: string;
};

/**
 * A tiny, dependency-free SVG sparkline for KPI tiles. Scales the series into
 * the box, draws a 1.5px line, an optional faint area, and a dot on the last
 * point. Sober, fund-grade; renders nothing for degenerate series.
 */
export default function Sparkline({
  values,
  color = "#6366f1",
  width = 72,
  height = 22,
  fill = true,
  className,
}: Props) {
  const gradId = useId();
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) return null;

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const stepX = w / (pts.length - 1);

  const x = (i: number) => pad + i * stepX;
  const y = (v: number) => pad + h - ((v - min) / span) * h;

  const line = pts.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(pts.length - 1).toFixed(1)},${(pad + h).toFixed(1)} L${pad.toFixed(1)},${(pad + h).toFixed(1)} Z`;
  const lastX = x(pts.length - 1);
  const lastY = y(pts[pts.length - 1]);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden
      preserveAspectRatio="none"
    >
      {fill && (
        <>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#${gradId})`} stroke="none" />
        </>
      )}
      <path d={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r={1.8} fill={color} />
    </svg>
  );
}
