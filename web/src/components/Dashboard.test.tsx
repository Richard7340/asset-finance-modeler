import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "./Dashboard";

vi.mock("../api", () => ({
  listAssets: vi.fn(),
  setLifecycle: vi.fn().mockResolvedValue({ id: "scn-2", lifecycle: "operational" }),
  getPortfolio: vi.fn().mockResolvedValue({ assets: [], totals: { npv: 0, capex: 0, revenue_y1: 0, count: 0 } }),
  // PortfolioAlerts + AssetsMap consume these for operational assets.
  getVariance: vi.fn().mockResolvedValue({ lines: [] }),
  getLive: vi.fn().mockResolvedValue({
    base: { kpis: {}, income_statement: { years: [], rows: {} }, cash_flow: { years: [], cfo: [], cfi: [], cff: [] } },
    live: { kpis: {}, income_statement: { years: [], rows: {} }, cash_flow: { years: [], cfo: [], cfi: [], cff: [] } },
    comparison: { npv_base: 0, npv_live: 0, delta: 0, irr_base: 0, irr_live: 0, dscr_min_base: 1.5, dscr_min_live: 1.5, elapsed_years: 0, n_years: 0 },
  }),
}));

import { listAssets, setLifecycle } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const ASSETS = [
  { id: "scn-1", name: "Planta", model_id: "solar_pv_50mw_spain", created_at: "2026-01-01T00:00:00Z", kpis: {}, lifecycle: "operational", commissioning_date: "2026-01-01T00:00:00Z", tracking_frequency: "monthly", lat: 37.39, lon: -5.99 },
  { id: "scn-2", name: "Oportunidad X", model_id: "bess_20mw_4h", created_at: "2026-02-01T00:00:00Z", kpis: {}, lifecycle: "opportunity", commissioning_date: null, tracking_frequency: null },
] as never[];

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Honour the lifecycle filter so each page gets only its own bucket.
    vi.mocked(listAssets).mockImplementation((lifecycle?: unknown) =>
      Promise.resolve(
        lifecycle
          ? (ASSETS.filter((a) => (a as { lifecycle: string }).lifecycle === lifecycle) as never)
          : (ASSETS as never),
      ),
    );
  });

  it("la página Cartera muestra solo activos en operación", async () => {
    wrap(<Dashboard page="cartera" onOpenAsset={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Cartera · activos en operación")).toBeTruthy();
    });
    expect(screen.queryByText("Oportunidades · valoraciones")).toBeNull();
  });

  it("la página Oportunidades muestra solo valoraciones", async () => {
    wrap(<Dashboard page="oportunidades" onOpenAsset={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Oportunidades · valoraciones")).toBeTruthy();
    });
    expect(screen.queryByText("Cartera · activos en operación")).toBeNull();
  });

  it("Marcar en operación promociona (setLifecycle operational) en Oportunidades", async () => {
    wrap(<Dashboard page="oportunidades" onOpenAsset={() => {}} />);
    const btns = await screen.findAllByText("Marcar en operación");
    fireEvent.click(btns[0]);
    await waitFor(() =>
      expect(setLifecycle).toHaveBeenCalledWith("scn-2", { lifecycle: "operational" }),
    );
  });

  it("Devolver a oportunidad degrada (setLifecycle opportunity) en Cartera", async () => {
    wrap(<Dashboard page="cartera" onOpenAsset={() => {}} />);
    const btns = await screen.findAllByText("Devolver a oportunidad");
    fireEvent.click(btns[0]);
    await waitFor(() =>
      expect(setLifecycle).toHaveBeenCalledWith("scn-1", { lifecycle: "opportunity" }),
    );
  });
});
