/** Format helpers for investor-facing KPIs. */

/** Format euros, switching to M€ for large values, otherwise k€. */
export function eur(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString("es-ES", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} M€`;
  }
  return `${(value / 1_000).toLocaleString("es-ES", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })} k€`;
}

/** Format euros with full digits (for dense tables). */
export function eurExact(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("es-ES", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

/** Format a multiple (×). */
export function mult(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${value.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}×`;
}

/** Format a percentage (value already in 0..1). */
export function pct(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toLocaleString("es-ES", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}%`;
}

/** Short date (es-ES) from an ISO string. */
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Long date + time for the "revisando" banner. */
export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
