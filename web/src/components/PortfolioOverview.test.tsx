import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import PortfolioOverview from "./PortfolioOverview";
import * as api from "../api";

const assets = [
  { id: "a1", name: "Planta Solar Sur", model_id: "solar", created_at: "2026-01-01T00:00:00Z", kpis: {} },
  { id: "a2", name: "BESS Norte", model_id: "bess", created_at: "2026-01-02T00:00:00Z", kpis: {} },
];

const portfolio = {
  assets: [
    { id: "a1", name: "Planta Solar Sur", model_id: "solar", npv: 3_000_000, revenue_y1: 800_000, capex: 5_000_000, irr: 0.082, yield_pct: 0.6 },
    { id: "a2", name: "BESS Norte", model_id: "bess", npv: 1_000_000, revenue_y1: 400_000, capex: 2_000_000, irr: 0.055, yield_pct: 0.5 },
  ],
  totals: { npv: 4_000_000, capex: 7_000_000, revenue_y1: 1_200_000, count: 2, irr_weighted: 0.072 },
};

beforeEach(() => {
  vi.spyOn(api, "listAssets").mockResolvedValue(assets as never);
  vi.spyOn(api, "getPortfolio").mockResolvedValue(portfolio as never);
});

afterEach(() => vi.restoreAllMocks());

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

test("leads with the assets (cards) and keeps the detail table reachable", async () => {
  renderWithClient(<PortfolioOverview onOpenAsset={() => {}} />);
  // Aggregate VAN total (4 M€). Appears in the KPI strip and the donut centre.
  const vanTotals = await screen.findAllByText(/4,00 M€/);
  expect(vanTotals.length).toBeGreaterThan(0);
  // The assets are the hero: each asset name appears (card + chart axis/legend).
  expect(screen.getAllByText("Planta Solar Sur").length).toBeGreaterThan(0);
  expect(screen.getAllByText("BESS Norte").length).toBeGreaterThan(0);
  // Contribution: a1 = 75% — shown on the card and in the composition legend.
  expect(screen.getAllByText(/75%/).length).toBeGreaterThan(0);
  // TIR for an asset (a1 IRR = 8.2%) renders on its card.
  expect(screen.getAllByText(/8,2%/).length).toBeGreaterThan(0);
  // Aggregate TIR media card (7.2%).
  expect(screen.getByText(/7,2%/)).toBeTruthy();
  // The dense detail table is collapsed by default but reachable via a toggle.
  expect(screen.getByText(/Ver tabla detallada/)).toBeTruthy();
  // The asset cards expose the include-in-aggregate toggle (one per asset).
  expect(screen.getAllByLabelText(/Incluir .* en el agregado/).length).toBe(2);
});
