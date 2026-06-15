import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import CurvesPanel, {
  isCurveNameInput,
  pointsPathFor,
  unitFromParameter,
} from "./CurvesPanel";
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
  expect(await screen.findByText(/Curva propia/)).toBeTruthy();
  expect(screen.getByText(/Valores definidos por el usuario/)).toBeTruthy();
});

test("derives the axis unit from the curve parameter", () => {
  expect(unitFromParameter("spread_eur_mwh")).toBe("EUR/MWh");
  expect(unitFromParameter("price_usd_kg")).toBe("USD/kg");
  expect(unitFromParameter("availability_pct")).toBe("%");
  expect(unitFromParameter("opaque_param")).toBe("");
});

test("edit grid → Aplicar applies the edited projection as a number[] points override", async () => {
  const onChangeOverride = vi.fn();
  renderWithClient(
    <CurvesPanel
      schema={schema}
      overrides={{}}
      onChangeOverride={onChangeOverride}
    />,
  );

  // Enter edit mode.
  const toggle = await screen.findByRole("button", { name: "Editar proyección" });
  fireEvent.click(toggle);

  // Edit Año 1 (prefilled from the library curve = 80).
  const yearOne = screen.getByLabelText("Año 1") as HTMLInputElement;
  fireEvent.change(yearOne, { target: { value: "123" } });

  // Apply → sets the sibling *_points override with a 30-length number[].
  fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

  expect(onChangeOverride).toHaveBeenCalledWith(
    "bess.revenue[0].spread_points",
    expect.any(Array),
  );
  const [, applied] = onChangeOverride.mock.calls[0];
  expect(Array.isArray(applied)).toBe(true);
  expect(applied).toHaveLength(30);
  expect(applied[0]).toBe(123);
  expect(applied.every((n: unknown) => typeof n === "number")).toBe(true);
});

test("Restaurar clears both the points and curve_name overrides", async () => {
  const onChangeOverride = vi.fn();
  renderWithClient(
    <CurvesPanel
      schema={schema}
      overrides={{ "bess.revenue[0].spread_points": [50, 49, 48] }}
      onChangeOverride={onChangeOverride}
    />,
  );
  const restore = await screen.findByRole("button", {
    name: "Restaurar curva de librería",
  });
  fireEvent.click(restore);
  expect(onChangeOverride).toHaveBeenCalledWith(
    "bess.revenue[0].spread_points",
    undefined,
  );
  expect(onChangeOverride).toHaveBeenCalledWith(
    "bess.revenue[0].spread_curve_name",
    undefined,
  );
});

test("% anual helper computes a geometric working array applied on Aplicar", async () => {
  const onChangeOverride = vi.fn();
  renderWithClient(
    <CurvesPanel schema={schema} overrides={{}} onChangeOverride={onChangeOverride} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Editar proyección" }));

  fireEvent.change(screen.getByLabelText("Valor base año 1"), {
    target: { value: "100" },
  });
  fireEvent.change(screen.getByLabelText("Crecimiento anual en porcentaje"), {
    target: { value: "10" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar crecimiento" }));
  fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

  const [, applied] = onChangeOverride.mock.calls[0];
  expect(applied[0]).toBe(100);
  expect(applied[1]).toBeCloseTo(110, 4);
  expect(applied[2]).toBeCloseTo(121, 4);
});

test("the editable grid exposes a cell for every year (1..30)", async () => {
  const onChangeOverride = vi.fn();
  renderWithClient(
    <CurvesPanel schema={schema} overrides={{}} onChangeOverride={onChangeOverride} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Editar proyección" }));
  expect(screen.getByLabelText("Año 1")).toBeTruthy();
  expect(screen.getByLabelText("Año 30")).toBeTruthy();
});
