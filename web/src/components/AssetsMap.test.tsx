import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AssetsMap from "./AssetsMap";

vi.mock("../api", () => ({
  listAssets: vi.fn(),
}));

import { listAssets } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const ASSETS = [
  {
    id: "a1",
    name: "FV Sevilla",
    model_id: "solar_pv_50mw_spain",
    created_at: "2026-01-01T00:00:00Z",
    kpis: { npv: 1_200_000 },
    lifecycle: "operational",
    commissioning_date: null,
    tracking_frequency: null,
    location: "Sevilla",
    lat: 37.39,
    lon: -5.99,
  },
  {
    id: "a2",
    name: "Sin coords",
    model_id: "bess_20mw_4h",
    created_at: "2026-01-01T00:00:00Z",
    kpis: { npv: 500_000 },
    lifecycle: "opportunity",
    commissioning_date: null,
    tracking_frequency: null,
    location: null,
    lat: null,
    lon: null,
  },
] as never[];

describe("AssetsMap", () => {
  it("monta y reporta cuantos activos tienen ubicacion y cuantos no", async () => {
    vi.mocked(listAssets).mockResolvedValue(ASSETS as never);
    wrap(<AssetsMap />);
    await waitFor(() => {
      // One plotted (a1), one without coords (a2).
      expect(screen.getByText(/1 con ubicación/)).toBeTruthy();
      expect(screen.getByText(/1 sin coordenadas/)).toBeTruthy();
    });
  });
});
