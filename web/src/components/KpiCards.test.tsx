import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import KpiCards from "./KpiCards";
import type { RunResult } from "../api";

const mock: RunResult = {
  kpis: {
    npv_fv: -998724,
    npv_bess: 2030600,
    npv_hybrid: 1031876,
    dscr_sub_min: 1.05,
    dscr_sub_avg: 1.2,
    dscr_senior_min: 1.4,
    moic_sub: 1.37,
    recovery: 1.0,
  },
  cashflows: { years: [1], fv: [0], bess: [0] },
  curves: { spread: [0], ancillary: [0] },
  bridge: { fv: 0, bess: 0, hybrid: 0 },
  dscr_profile: [1],
};

test("renders MOIC sub value", () => {
  render(<KpiCards data={mock} />);
  expect(screen.getByText(/1,37×/)).toBeTruthy();
});
