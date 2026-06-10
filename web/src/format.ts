/** Format helpers for investor-facing KPIs. */

/** Format euros, switching to M€ for large values, otherwise k€. */
export function eur(value: number): string {
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

/** Format a multiple (×). */
export function mult(value: number): string {
  return `${value.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}×`;
}

/** Format a percentage (value already in 0..1). */
export function pct(value: number): string {
  return `${(value * 100).toLocaleString("es-ES", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}%`;
}
