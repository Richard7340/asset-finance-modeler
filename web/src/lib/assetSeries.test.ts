import { describe, expect, test } from "vitest";
import { assetAnnualSeries, consolidateSeries } from "./assetSeries";
import type { RunResult } from "../api";

describe("assetAnnualSeries", () => {
  test("prefers net income from the income statement", () => {
    const snap = {
      income_statement: {
        years: [1, 2, 3],
        rows: { net_income: [100, 200, 300] },
      },
      cash_flow: { years: [1, 2, 3], cfo: [9, 9, 9], cfi: [], cff: [] },
    } as unknown as RunResult;
    expect(assetAnnualSeries(snap)).toEqual([100, 200, 300]);
  });

  test("falls back to CFO when there is no net income line", () => {
    const snap = {
      cash_flow: { years: [1, 2], cfo: [50, 60], cfi: [], cff: [] },
    } as unknown as RunResult;
    expect(assetAnnualSeries(snap)).toEqual([50, 60]);
  });

  test("falls back to combined hybrid cashflows", () => {
    const snap = {
      cashflows: { years: [1, 2], fv: [10, 20], bess: [1, 2] },
    } as unknown as RunResult;
    expect(assetAnnualSeries(snap)).toEqual([11, 22]);
  });

  test("returns [] for an unreadable / null snapshot", () => {
    expect(assetAnnualSeries(null)).toEqual([]);
    expect(assetAnnualSeries({} as RunResult)).toEqual([]);
  });
});

describe("consolidateSeries", () => {
  test("sums aligned series", () => {
    expect(consolidateSeries([[1, 2, 3], [10, 20, 30]])).toEqual([11, 22, 33]);
  });

  test("pads shorter horizons with zero", () => {
    expect(consolidateSeries([[1, 2, 3], [10, 20]])).toEqual([11, 22, 3]);
  });

  test("ignores empty series and returns [] when nothing usable", () => {
    expect(consolidateSeries([[], []])).toEqual([]);
    expect(consolidateSeries([[5, 5], []])).toEqual([5, 5]);
  });
});
