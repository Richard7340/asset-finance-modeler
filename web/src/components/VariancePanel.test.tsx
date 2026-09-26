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

describe("VariancePanel: el año en curso y mes a mes (27-sep)", () => {
  it("compara el año en curso con lo previsto hasta hoy y enseña los meses", async () => {
    vi.mocked(getVariance).mockResolvedValue({
      lines: [
        {
          line_path: "lineas.gastos.IBI", label: "IBI", unit: "EUR",
          base: [1200, 1236], actual: [700, null], deviation: [-200, null], deviation_pct: [-0.2222, null],
          cumulative_actual: 700, cumulative_base: 900, fulfillment_pct: 0.7778,
          base_comparada: [900, null], anio_en_curso: 0, fraccion_del_anio: 0.75,
          mensual: [
            { mes: 1, real: 300, prevision: 100 }, { mes: 2, real: 400, prevision: 100 },
            ...Array.from({ length: 10 }, (_, i) => ({ mes: i + 3, real: null, prevision: 100 })),
          ],
        },
      ],
    });
    wrap(<VariancePanel assetId="a1" />);
    await waitFor(() => expect(screen.getByText("Este año, mes a mes")).toBeTruthy());
    expect(screen.getByText(/en curso/)).toBeTruthy();
    // Lo previsto hasta hoy (900), con el año entero (1.200) a mano.
    expect(screen.getByTitle(/Año entero: 1\.?200/).textContent).toBe("900");
    expect(screen.getAllByText("Feb").length).toBeGreaterThan(0);
  });
});

import { esLineaDeGasto } from "./VariancePanel";
describe("colores de un gasto (27-sep)", () => {
  it("un gasto se reconoce por su ruta o nombre", () => {
    expect(esLineaDeGasto({ line_path: "lineas.gastos.IBI", label: "IBI" })).toBe(true);
    expect(esLineaDeGasto({ line_path: "lineas.ingresos.Rentas", label: "Rentas" })).toBe(false);
  });
});
