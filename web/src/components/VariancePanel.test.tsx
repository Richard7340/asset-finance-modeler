import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import VariancePanel from "./VariancePanel";

vi.mock("../api", () => ({
  getVariance: vi.fn(),
}));

import { getVariance } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("VariancePanel", () => {
  beforeEach(() => {
    vi.mocked(getVariance).mockResolvedValue({
      lines: [
        {
          line_path: "income_statement.rows.revenue",
          label: "Ingresos",
          unit: "EUR",
          base: [1000, 1100, 1200],
          actual: [950, null, null],
          deviation: [-50, null, null],
          deviation_pct: [-0.05, null, null],
          cumulative_actual: 950,
          cumulative_base: 1000,
          fulfillment_pct: 0.95,
        },
        {
          line_path: "cash_flow.cfo",
          label: "Flujo de operaciones",
          unit: "EUR",
          base: [500, 550, 600],
          actual: [null, null, null],
          deviation: [null, null, null],
          deviation_pct: [null, null, null],
          cumulative_actual: 0,
          cumulative_base: 0,
          fulfillment_pct: null,
        },
      ],
    } as never);
  });

  it("renderiza base y real solo para las líneas con datos", async () => {
    wrap(<VariancePanel assetId="scn-1" />);

    // The tracked line (revenue, has an actual) is shown.
    await waitFor(() => expect(screen.getByText("Ingresos")).toBeTruthy());
    // The untracked line (cfo, all null) is hidden.
    expect(screen.queryByText("Flujo de operaciones")).toBeNull();
    // Base value (1000, with or without thousands separator) and the real
    // value (950) render.
    expect(screen.getAllByText(/1.?000/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("950").length).toBeGreaterThan(0);
    expect(screen.getAllByText("95%").length).toBeGreaterThan(0);
  });
});
