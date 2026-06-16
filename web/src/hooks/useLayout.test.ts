import { describe, expect, test } from "vitest";
import {
  clamp,
  normalizeLayout,
  DEFAULT_LAYOUT,
  NAV_MAX,
  INPUTS_MIN,
} from "./useLayout";

describe("clamp", () => {
  test("keeps values inside the range", () => {
    expect(clamp(300, 180, 420, 264)).toBe(300);
  });
  test("clamps below min and above max", () => {
    expect(clamp(50, 180, 420, 264)).toBe(180);
    expect(clamp(9999, 180, 420, 264)).toBe(420);
  });
  test("falls back on non-finite input", () => {
    expect(clamp(NaN, 180, 420, 264)).toBe(264);
  });
});

describe("normalizeLayout", () => {
  test("returns defaults for garbage / missing input", () => {
    expect(normalizeLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout("nope")).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout(undefined)).toBeTruthy();
  });

  test("clamps persisted widths to legal ranges", () => {
    const out = normalizeLayout({ navWidth: 5000, inputsWidth: 10 });
    expect(out.navWidth).toBe(NAV_MAX);
    expect(out.inputsWidth).toBe(INPUTS_MIN);
  });

  test("preserves collapsed flags and section map", () => {
    const out = normalizeLayout({
      navCollapsed: true,
      inputsCollapsed: false,
      sections: { revenue: true, capex: false },
    });
    expect(out.navCollapsed).toBe(true);
    expect(out.inputsCollapsed).toBe(false);
    expect(out.sections.revenue).toBe(true);
    expect(out.sections.capex).toBe(false);
  });

  test("a valid round-trip survives normalization", () => {
    const valid = {
      navWidth: 300,
      inputsWidth: 400,
      navCollapsed: false,
      inputsCollapsed: true,
      sections: { opex: true },
    };
    expect(normalizeLayout(valid)).toEqual(valid);
  });
});
