import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LivePanel from "./LivePanel";

vi.mock("../api", () => ({
  getLive: vi.fn(),
}));

import { getLive } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const RESULT = {
  base: {
    kpis: { npv: 1_000_000, irr_project: 0.08, dscr_min: 1.2, dscr_avg: 1.4 },
    income_statement: {
      years: [1, 2, 3],
      rows: {
        revenue: [100, 110, 120],
        ebitda: [60, 66, 72],
        ebit: [40, 44, 48],
        interest_expense: [10, 9, 8],
        ebt: [30, 35, 40],
        tax: [8, 9, 10],
        net_income: [22, 26, 30],
      },
    },
    cash_flow: { years: [1, 2, 3], cfo: [50, 55, 60], cfi: [-200, 0, 0], cff: [150, -10, -10] },
  },
  live: {
    kpis: { npv: 1_300_000, irr_project: 0.1, dscr_min: 1.25, dscr_avg: 1.45 },
    income_statement: {
      years: [1, 2, 3],
      rows: {
        revenue: [130, 110, 120],
        ebitda: [78, 66, 72],
        ebit: [52, 44, 48],
        interest_expense: [10, 9, 8],
        ebt: [42, 35, 40],
        tax: [11, 9, 10],
        net_income: [31, 26, 30],
      },
    },
    cash_flow: { years: [1, 2, 3], cfo: [65, 55, 60], cfi: [-200, 0, 0], cff: [150, -10, -10] },
  },
  comparison: {
    npv_base: 1_000_000,
    npv_live: 1_300_000,
    delta: 300_000,
    irr_base: 0.08,
    irr_live: 0.1,
    dscr_min_base: 1.2,
    dscr_min_live: 1.25,
    elapsed_years: 1,
    n_years: 3,
  },
};

describe("LivePanel", () => {
  beforeEach(() => {
    vi.mocked(getLive).mockResolvedValue(RESULT as never);
  });

  it("renderiza base vs live con delta positivo", async () => {
    wrap(<LivePanel assetId="scn-1" />);

    // Header.
    await waitFor(() =>
      expect(screen.getAllByText(/Reproyección viva/i).length).toBeGreaterThan(0),
    );
    // Three head-to-head KPI labels.
    expect(screen.getByText("VAN")).toBeTruthy();
    expect(screen.getByText("TIR proyecto")).toBeTruthy();
    expect(screen.getByText("DSCR mín")).toBeTruthy();
    // The base NPV (1,00 M€) appears as the muted "Base" reference.
    expect(screen.getAllByText(/1,00 M€/).length).toBeGreaterThan(0);
    // The live NPV (1,30 M€) is shown as the primary value.
    expect(screen.getAllByText(/1,30 M€/).length).toBeGreaterThan(0);
    // The positive delta (+300 k€) carries a + sign. The value sits in a span
    // alongside the up-arrow icon, so match on the span's normalised text.
    const deltaEls = screen.getAllByText(
      (_, el) => el?.tagName === "SPAN" && el.textContent === "+300 k€",
    );
    expect(deltaEls.length).toBeGreaterThan(0);
  });
});
