import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ActualsGrid from "./ActualsGrid";

vi.mock("../api", () => ({
  getLines: vi.fn(),
  getActuals: vi.fn(),
  postActuals: vi.fn().mockResolvedValue({ ids: ["act-1"] }),
  deleteActual: vi.fn().mockResolvedValue(undefined),
}));

import { getLines, getActuals, postActuals } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const LINES = [
  { path: "income_statement.rows.revenue", label: "Ingresos", unit: "EUR" },
  { path: "cash_flow.cfo", label: "Flujo de operaciones", unit: "EUR" },
];

describe("ActualsGrid", () => {
  beforeEach(() => {
    vi.mocked(getLines).mockResolvedValue(LINES as never);
    vi.mocked(getActuals).mockResolvedValue([] as never);
    vi.mocked(postActuals).mockClear();
  });

  it("guarda un dato real con el path y valor correctos", async () => {
    wrap(<ActualsGrid assetId="scn-1" trackingFrequency="monthly" />);

    // The selector defaults to the first line.
    await waitFor(() => expect(screen.getByLabelText("Línea")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Fecha del periodo"), {
      target: { value: "2026-03-01" },
    });
    fireEvent.change(screen.getByLabelText("Valor real"), {
      target: { value: "1234" },
    });
    fireEvent.click(screen.getByText("Añadir"));

    await waitFor(() =>
      expect(postActuals).toHaveBeenCalledWith("scn-1", [
        expect.objectContaining({
          period_start: "2026-03-01",
          line_path: "income_statement.rows.revenue",
          value: 1234,
        }),
      ]),
    );
  });

  it("muestra los datos reales existentes", async () => {
    vi.mocked(getActuals).mockResolvedValue([
      {
        id: "act-1",
        period_start: "2026-02-01",
        line_path: "income_statement.rows.revenue",
        value: 5000,
        unit: "EUR",
        note: "febrero",
        entered_by: "default",
        entered_at: "2026-02-02T00:00:00Z",
      },
    ] as never);

    wrap(<ActualsGrid assetId="scn-1" trackingFrequency="monthly" />);

    await waitFor(() => expect(screen.getByText("febrero")).toBeTruthy());
  });
});
