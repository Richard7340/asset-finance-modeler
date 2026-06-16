import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Detail-view layout preferences, persisted in localStorage under `afm-layout`.
 *
 * Holds the two resizable column widths (asset navigator + input editor), the
 * collapsed state of each of those panels, and the collapsed state of every
 * input section (keyed by section key). Restored on load so the user's layout
 * sticks across sessions and across switching assets.
 *
 * This is purely layout state — it lives in App, not in `useRun`'s query key,
 * so resizing/collapsing never retriggers a model recalc.
 */

export const LAYOUT_KEY = "afm-layout";

export const NAV_MIN = 180;
export const NAV_MAX = 420;
export const NAV_DEFAULT = 264;

export const INPUTS_MIN = 260;
export const INPUTS_MAX = 560;
export const INPUTS_DEFAULT = 336;

export type LayoutState = {
  /** Asset-navigator column width in px. */
  navWidth: number;
  /** Input-editor column width in px. */
  inputsWidth: number;
  /** Navigator collapsed to a thin rail. */
  navCollapsed: boolean;
  /** Input editor collapsed to a thin rail. */
  inputsCollapsed: boolean;
  /** Per-section collapsed flags (true = collapsed). Keyed by section key. */
  sections: Record<string, boolean>;
};

export const DEFAULT_LAYOUT: LayoutState = {
  navWidth: NAV_DEFAULT,
  inputsWidth: INPUTS_DEFAULT,
  navCollapsed: false,
  inputsCollapsed: false,
  sections: {},
};

/** Clamp a value to [min, max], coercing non-finite numbers to the fallback. */
export function clamp(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

/**
 * Merge a (possibly partial / untrusted) persisted blob onto the defaults,
 * clamping widths to their legal ranges. Exported so it can be unit-tested
 * without touching the DOM/localStorage.
 */
export function normalizeLayout(raw: unknown): LayoutState {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_LAYOUT };
  const r = raw as Partial<LayoutState>;
  return {
    navWidth: clamp(Number(r.navWidth), NAV_MIN, NAV_MAX, NAV_DEFAULT),
    inputsWidth: clamp(Number(r.inputsWidth), INPUTS_MIN, INPUTS_MAX, INPUTS_DEFAULT),
    navCollapsed: r.navCollapsed === true,
    inputsCollapsed: r.inputsCollapsed === true,
    sections:
      r.sections && typeof r.sections === "object"
        ? { ...(r.sections as Record<string, boolean>) }
        : {},
  };
}

function readInitial(): LayoutState {
  if (typeof window === "undefined") return { ...DEFAULT_LAYOUT };
  try {
    const stored = window.localStorage.getItem(LAYOUT_KEY);
    if (!stored) return { ...DEFAULT_LAYOUT };
    return normalizeLayout(JSON.parse(stored));
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

export type UseLayout = {
  layout: LayoutState;
  setNavWidth: (px: number) => void;
  setInputsWidth: (px: number) => void;
  toggleNav: () => void;
  toggleInputs: () => void;
  /** True if the section is collapsed. `fallback` applies when never set. */
  isSectionCollapsed: (key: string, fallback: boolean) => boolean;
  toggleSection: (key: string, fallback: boolean) => void;
};

export function useLayout(): UseLayout {
  const [layout, setLayout] = useState<LayoutState>(readInitial);

  // Persist on every change (debounced via rAF would be overkill; writes are
  // cheap and only happen on pointerup / clicks, not on every pointermove —
  // see the divider handlers which commit on release).
  const latest = useRef(layout);
  latest.current = layout;
  useEffect(() => {
    try {
      window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
    } catch {
      // Ignore storage failures (private mode, quota, etc.).
    }
  }, [layout]);

  const setNavWidth = useCallback((px: number) => {
    setLayout((p) => ({ ...p, navWidth: clamp(px, NAV_MIN, NAV_MAX, NAV_DEFAULT) }));
  }, []);

  const setInputsWidth = useCallback((px: number) => {
    setLayout((p) => ({
      ...p,
      inputsWidth: clamp(px, INPUTS_MIN, INPUTS_MAX, INPUTS_DEFAULT),
    }));
  }, []);

  const toggleNav = useCallback(
    () => setLayout((p) => ({ ...p, navCollapsed: !p.navCollapsed })),
    [],
  );
  const toggleInputs = useCallback(
    () => setLayout((p) => ({ ...p, inputsCollapsed: !p.inputsCollapsed })),
    [],
  );

  const isSectionCollapsed = useCallback(
    (key: string, fallback: boolean) => {
      const v = latest.current.sections[key];
      return v === undefined ? fallback : v;
    },
    [],
  );

  const toggleSection = useCallback((key: string, fallback: boolean) => {
    setLayout((p) => {
      const cur = p.sections[key] === undefined ? fallback : p.sections[key];
      return { ...p, sections: { ...p.sections, [key]: !cur } };
    });
  }, []);

  return {
    layout,
    setNavWidth,
    setInputsWidth,
    toggleNav,
    toggleInputs,
    isSectionCollapsed,
    toggleSection,
  };
}
