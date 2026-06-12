/**
 * Animation primitives (animejs v4), guarded so they degrade gracefully in
 * jsdom / SSR / reduced-motion. Nothing here ever throws when the DOM or
 * requestAnimationFrame is missing — components always render their final
 * state so tests can read the final values as plain text.
 */
import { animate, stagger, utils } from "animejs";

/** True only in a real browser with rAF available (not jsdom/SSR). */
export const canAnimate =
  typeof window !== "undefined" &&
  typeof requestAnimationFrame === "function" &&
  // jsdom reports this; real browsers + reduced-motion handled per-call
  typeof document !== "undefined";

/** Respect the user's reduced-motion preference. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Whether motion should actually run. */
export function motionEnabled(): boolean {
  return canAnimate && !prefersReducedMotion();
}

export { animate, stagger, utils };
