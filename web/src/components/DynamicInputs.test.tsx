import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import DynamicInputs from "./DynamicInputs";
import * as api from "../api";
import type { ModelSchema, OverrideValue } from "../api";

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

beforeEach(() => {
  vi.spyOn(api, "getCurves").mockResolvedValue({ curves } as never);
});
afterEach(() => vi.restoreAllMocks());

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

type Setters = {
  onChangeNumber: ReturnType<typeof vi.fn>;
  onChangeOverride: ReturnType<typeof vi.fn>;
};

function renderInputs(schema: ModelSchema, overrides: api.Overrides = {}): Setters {
  const onChangeNumber = vi.fn();
  const onChangeOverride = vi.fn();
  renderWithClient(
    <DynamicInputs
      schema={schema}
      overrides={overrides}
      onChangeNumber={onChangeNumber}
      onChangeOverride={onChangeOverride}
    />,
  );
  return { onChangeNumber, onChangeOverride };
}

const boolSchema: ModelSchema = {
  inputs: [
    {
      path: "taxes.enabled",
      value: false,
      type: "bool",
      section: "taxes",
      label: "enabled",
    },
  ],
};

const textSchema: ModelSchema = {
  inputs: [
    {
      path: "revenue.currency",
      value: "EUR",
      type: "text",
      section: "revenue",
      label: "currency",
    },
  ],
};

test("FIX A: bool input renders as a toggle and edits via the override setter", () => {
  const { onChangeOverride } = renderInputs(boolSchema);
  const toggle = screen.getByLabelText("Enabled") as HTMLInputElement;
  expect(toggle.type).toBe("checkbox");
  expect(toggle.checked).toBe(false);
  fireEvent.click(toggle);
  expect(onChangeOverride).toHaveBeenCalledWith("taxes.enabled", true);
});

test("FIX A: bool input reflects an active boolean override", () => {
  const { onChangeOverride } = renderInputs(boolSchema, { "taxes.enabled": true });
  const toggle = screen.getByLabelText("Enabled") as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  fireEvent.click(toggle);
  expect(onChangeOverride).toHaveBeenCalledWith("taxes.enabled", false);
});

test("FIX A: text/enum input is editable and commits a string override", () => {
  const { onChangeOverride } = renderInputs(textSchema);
  const input = screen.getByLabelText("Currency") as HTMLInputElement;
  expect(input.type).toBe("text");
  expect(input.value).toBe("EUR");
  fireEvent.change(input, { target: { value: "USD" } });
  expect(onChangeOverride).toHaveBeenCalledWith("revenue.currency", "USD");
});

test("FIX A: clearing a text input removes the override (revert to default)", () => {
  const { onChangeOverride } = renderInputs(textSchema, { "revenue.currency": "USD" });
  const input = screen.getByLabelText("Currency") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "" } });
  expect(onChangeOverride).toHaveBeenCalledWith("revenue.currency", undefined);
});

const numberSchema: ModelSchema = {
  inputs: [
    {
      path: "capex.total",
      value: 1000,
      type: "number",
      section: "capex",
      label: "CAPEX",
    },
  ],
};

test("FIX B: clearing a number input removes the override instead of forcing 0", () => {
  const { onChangeNumber, onChangeOverride } = renderInputs(numberSchema, {
    "capex.total": 1500,
  });
  // open the capex section is default-open (index 0) — find the input
  const input = screen.getByDisplayValue("1500") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "" } });
  expect(onChangeOverride).toHaveBeenCalledWith("capex.total", undefined);
  expect(onChangeNumber).not.toHaveBeenCalledWith("capex.total", 0);
});

test("FIX B: a real numeric edit still flows through onChangeNumber", () => {
  const { onChangeNumber } = renderInputs(numberSchema);
  const input = screen.getByDisplayValue("1000") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "2000" } });
  expect(onChangeNumber).toHaveBeenCalledWith("capex.total", 2000);
});

const curveGovernedSchema: ModelSchema = {
  inputs: [
    {
      path: "revenue[0].price_curve_name",
      value: "spread_da_es",
      type: "text",
      section: "revenue",
      label: "price curve name",
    },
    {
      path: "revenue[0].base_price",
      value: 50,
      type: "number",
      section: "revenue",
      label: "base price",
    },
    {
      path: "revenue[0].volume_fraction",
      value: 1,
      type: "number",
      section: "revenue",
      label: "volume fraction",
    },
  ],
};

test("FIX C: a price scalar superseded by an active curve shows the hint", async () => {
  renderInputs(curveGovernedSchema);
  // The curve_name has a non-empty schema default → base_price is governed.
  expect(await screen.findByText("definido por la curva")).toBeTruthy();
});

test("FIX C: an unrelated scalar (volume_fraction) is not flagged", async () => {
  renderInputs(curveGovernedSchema);
  await screen.findByText("definido por la curva");
  // Only the price-family scalar should carry the hint, not volume_fraction.
  expect(screen.getAllByText("definido por la curva")).toHaveLength(1);
});

test("LAYOUT: a section header collapses/expands its body", () => {
  // capex is default-open (first section); clicking the header should hide
  // its input, clicking again should reveal it.
  const { onChangeNumber } = renderInputs(numberSchema);
  expect(onChangeNumber).not.toHaveBeenCalled();
  expect(screen.queryByDisplayValue("1000")).toBeTruthy();
  const header = screen.getByRole("button", { name: /Inversión|capex/i });
  fireEvent.click(header);
  expect(screen.queryByDisplayValue("1000")).toBeNull();
  fireEvent.click(header);
  expect(screen.queryByDisplayValue("1000")).toBeTruthy();
});

test("LAYOUT: section collapse delegates to the layout store when wired", () => {
  const onChangeNumber = vi.fn();
  const onChangeOverride = vi.fn();
  const collapsed: Record<string, boolean> = {};
  const isSectionCollapsed = vi.fn(
    (key: string, fallback: boolean) =>
      collapsed[key] === undefined ? fallback : collapsed[key],
  );
  const toggleSection = vi.fn((key: string, fallback: boolean) => {
    const cur = collapsed[key] === undefined ? fallback : collapsed[key];
    collapsed[key] = !cur;
  });
  renderWithClient(
    <DynamicInputs
      schema={numberSchema}
      overrides={{}}
      onChangeNumber={onChangeNumber}
      onChangeOverride={onChangeOverride}
      isSectionCollapsed={isSectionCollapsed}
      toggleSection={toggleSection}
    />,
  );
  const header = screen.getByRole("button", { name: /Inversión|capex/i });
  fireEvent.click(header);
  expect(toggleSection).toHaveBeenCalledWith("capex", expect.any(Boolean));
});

const _typeCheck: OverrideValue = true; // boolean is a valid OverrideValue
void _typeCheck;
