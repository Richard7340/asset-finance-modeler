import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import AssetCards, { type AssetCardRow } from "./AssetCards";
import type { PortfolioAsset, SavedAssetSummary } from "../api";

function makeRow(over: Partial<AssetCardRow> = {}): AssetCardRow {
  return {
    id: "scn-1",
    name: "Planta FV Sevilla",
    model_id: "bess_20mw_4h",
    location: "Sevilla",
    ...over,
  };
}

function makeMetrics(): Map<string, PortfolioAsset> {
  const m = new Map<string, PortfolioAsset>();
  m.set("scn-1", {
    id: "scn-1",
    name: "Planta FV Sevilla",
    model_id: "bess_20mw_4h",
    npv: 1_250_000,
    irr: 0.12,
    revenue_y1: 800_000,
    capex: 5_000_000,
    yield_pct: 0.25,
  });
  return m;
}

function renderCards(row: AssetCardRow) {
  return render(
    <AssetCards
      rows={[row]}
      metricsById={makeMetrics()}
      seriesById={new Map([["scn-1", [100, 120, 140]]])}
      excluded={new Set()}
      totalNpv={2_500_000}
      lifecycle="operational"
      onToggle={() => {}}
      onOpen={() => {}}
      resolveAsset={() => undefined}
    />,
  );
}

test("shows the relative last-updated line with an absolute tooltip", () => {
  const iso = new Date(Date.now() - 3 * 86_400_000).toISOString();
  renderCards(makeRow({ last_update: iso, tracking_frequency: "monthly" }));
  const line = screen.getByText(/Actualizado hace 3 días/);
  expect(line).toBeTruthy();
  // Absolute timestamp is exposed in the title tooltip on the wrapper.
  const wrapper = line.closest("[title]");
  expect(wrapper?.getAttribute("title")).toMatch(/Última actualización:/);
});

test("renders 'hoy' for a fresh update and the primary VAN figure", () => {
  renderCards(makeRow({ last_update: new Date().toISOString(), tracking_frequency: "monthly" }));
  expect(screen.getByText(/Actualizado hoy/)).toBeTruthy();
  // VAN is the primary metric (1,25 M€ from 1_250_000).
  expect(screen.getByText(/1,25 M€/)).toBeTruthy();
});

test("omits the updated line when no timestamp is provided", () => {
  renderCards(makeRow({ last_update: undefined }));
  expect(screen.queryByText(/Actualizado/)).toBeNull();
});

// Sanity: type guard so SavedAssetSummary carries last_update.
test("SavedAssetSummary type carries last_update", () => {
  const s: SavedAssetSummary = {
    id: "x",
    name: "x",
    model_id: "m",
    created_at: "2026-01-01T00:00:00Z",
    last_update: "2026-01-02T00:00:00Z",
    kpis: {},
    lifecycle: "opportunity",
    commissioning_date: null,
    tracking_frequency: null,
  };
  expect(s.last_update).toBe("2026-01-02T00:00:00Z");
});
