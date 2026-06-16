import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AssetAlerts } from "./Alerts";

vi.mock("../api", () => ({
  getVariance: vi.fn(),
  getLive: vi.fn(),
  listAssets: vi.fn(),
}));

import { getVariance, getLive } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const okLive = {
  base: { kpis: {}, income_statement: { years: [], rows: {} }, cash_flow: { years: [], cfo: [], cfi: [], cff: [] } },
  live: { kpis: {}, income_statement: { years: [], rows: {} }, cash_flow: { years: [], cfo: [], cfi: [], cff: [] } },
  comparison: { npv_base: 0, npv_live: 0, delta: 0, irr_base: 0, irr_live: 0, dscr_min_base: 1.5, dscr_min_live: 1.5, elapsed_years: 1, n_years: 10 },
};

describe("AssetAlerts", () => {
  it("marca una desviacion por encima del 10%", async () => {
    vi.mocked(getVariance).mockResolvedValue({
      lines: [
        {
          line_path: "income_statement.rows.revenue",
          label: "Ingresos",
          unit: "",
          base: [100, 100],
          actual: [70, null],
          deviation: [-30, null],
          deviation_pct: [-0.3, null],
          cumulative_actual: 70,
          cumulative_base: 100,
          fulfillment_pct: 0.7,
        },
      ],
    } as never);
    vi.mocked(getLive).mockResolvedValue(okLive as never);
    wrap(<AssetAlerts assetId="a1" />);
    await waitFor(() => {
      expect(screen.getByText(/desviación/)).toBeTruthy();
      expect(screen.getByText(/-30/)).toBeTruthy();
    });
  });

  it("no marca nada cuando todo esta dentro de umbral", async () => {
    vi.mocked(getVariance).mockResolvedValue({ lines: [] } as never);
    vi.mocked(getLive).mockResolvedValue(okLive as never);
    wrap(<AssetAlerts assetId="a2" />);
    await waitFor(() => {
      expect(screen.getByText(/sin alertas/)).toBeTruthy();
    });
  });
});
