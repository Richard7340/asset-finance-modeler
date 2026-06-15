import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import CurvesPanel, { isCurveNameInput, pointsPathFor } from "./CurvesPanel";
import * as api from "../api";
import type { ModelSchema } from "../api";

const curves = [
  {
    name: "spread_da_es",
    source: "Agere TB2 España + Modo Energy",
    parameter: "spread_eur_mwh",
    asset_type: "bess",
    bankable: true,
    values: Array.from({ length: 30 }, (_, i) => 80 - i),
  },
];

const schema: ModelSchema = {
  inputs: [
    {
      path: "bess.revenue[0].spread_curve_name",
      value: "spread_da_es",
      type: "text",
      section: "revenue",
      label: "Curva de spread",
    },
    { path: "capex.total", value: 1000, type: "number", section: "capex", label: "CAPEX" },
  ],
};

beforeEach(() => {
  vi.spyOn(api, "getCurves").mockResolvedValue({ curves } as never);
});
afterEach(() => vi.restoreAllMocks());

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

test("detects curve_name inputs and maps to the points sibling", () => {
  expect(isCurveNameInput(schema.inputs[0])).toBe(true);
  expect(isCurveNameInput(schema.inputs[1])).toBe(false);
  expect(pointsPathFor("bess.revenue[0].spread_curve_name")).toBe(
    "bess.revenue[0].spread_points",
  );
});

test("renders the selected curve name and its consultant source for TDD review", async () => {
  renderWithClient(<CurvesPanel schema={schema} overrides={{}} />);
  expect(await screen.findByText("Curvas de mercado y fuentes")).toBeTruthy();
  expect(await screen.findByText(/Agere TB2 España \+ Modo Energy/)).toBeTruthy();
  expect(screen.getByText("spread_da_es")).toBeTruthy();
  expect(screen.getByText("Bankable")).toBeTruthy();
});

test("labels a user-supplied custom curve", async () => {
  renderWithClient(
    <CurvesPanel
      schema={schema}
      overrides={{ "bess.revenue[0].spread_points": [50, 49, 48] }}
    />,
  );
  expect(await screen.findByText("Curva propia")).toBeTruthy();
  expect(screen.getByText(/Valores definidos por el usuario/)).toBeTruthy();
});
