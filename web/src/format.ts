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

/**
 * Human "freshness" label for a timestamp, es-ES: "hoy", "ayer", "hace N días",
 * "hace N meses", and the absolute short date for anything older than ~a year.
 * Used for the per-asset "Actualizado …" line; pair with `fmtDate` for the
 * exact value in a tooltip.
 */
export function fmtRelative(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const ms = now.getTime() - d.getTime();
  if (ms < 0) return "hoy"; // clock skew / future stamp — treat as fresh
  const days = Math.floor(ms / 86_400_000);
  if (days === 0) return "hoy";
  if (days === 1) return "ayer";
  if (days < 30) return `hace ${days} días`;
  const months = Math.floor(days / 30);
  if (months < 12) return `hace ${months} ${months === 1 ? "mes" : "meses"}`;
  return fmtDate(iso);
}

/**
 * Whether a timestamp is "fresh" relative to a tracking cadence — drives the
 * calm freshness dot. Operational assets are expected to be kept current within
 * their tracking window (with a grace factor); opportunities have no cadence, so
 * a generous default keeps recently-saved ones calm without ever alarming.
 */
export function isFresh(
  iso: string,
  frequency?: "daily" | "monthly" | "quarterly" | null,
  now: Date = new Date(),
): boolean {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  const days = (now.getTime() - d.getTime()) / 86_400_000;
  if (days < 0) return true;
  const windowDays =
    frequency === "daily"
      ? 3
      : frequency === "monthly"
        ? 45
        : frequency === "quarterly"
          ? 135
          : 45; // opportunities / untracked: ~6 weeks grace
  return days <= windowDays;
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
