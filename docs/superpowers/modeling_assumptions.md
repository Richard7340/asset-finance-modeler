# Modeling assumptions — deliberate decisions (not bugs)

This document records the **deliberate modeling decisions** of the asset-finance
engine: choices that are conservative, defensible, and intentional. None of
these are bugs. Where a more sophisticated treatment is possible, it is noted as
a future refinement. This complements the per-fix rationale in the remediation
plan (`docs/superpowers/plans/2026-06-16-engine-remediation-all-assets.md`).

Last updated: closing FASE P3 (2026-06-16).

---

## DSCR uses EBITDA as the CFADS proxy

The Debt Service Coverage Ratio (and debt sizing) score the debt against
**EBITDA** as a proxy for Cash Flow Available for Debt Service (CFADS), rather
than a fully-built CFADS (EBITDA − cash taxes − maintenance capex ± ΔWC −
reserve movements).

- **Where:** `InfrastructureModel._compute_debt` / `_compute_kpis`
  (`src/.../infrastructure/model.py`), `core/financing.py::size_debt`,
  `HybridProject.run` (`src/.../hybrid/model.py`).
- **Why:** EBITDA is the standard first-pass CFADS proxy for renewable/infra
  project finance term sheets; for asset-heavy, low-WC projects with deferred
  taxes it is close to true CFADS. It keeps sizing transparent and matches the
  validated hybrid consolidated deal.
- **Implication:** DSCR is slightly optimistic versus a full CFADS where cash
  taxes / maintenance capex are material.
- **Future refinement:** migrate to a true CFADS series.

## PPA-on-BESS ignores the charging cost (proxy)

When a BESS carries a PPA / arbitrage revenue stream, the revenue is modeled on
the **discharged** energy (energy_cap × DoD × RTE × cycles × spread × capture)
without separately subtracting the **cost of charging energy**.

- **Where:** `infrastructure/engines/revenue.py::_arbitrage`.
- **Why:** the `avg_spread_eur_mwh` (and the spread curve) is a **net** spread —
  it already embeds the buy/sell differential, so a separate charging-cost line
  would double-count. Round-trip efficiency captures the energy loss.
- **Implication:** the model assumes the configured spread is net of charging;
  a gross spread would overstate margin.
- **Future refinement:** an explicit charge-energy cost line driven by a
  charging-price curve, for users who prefer to model gross spreads.

## Datacenter tier / redundancy are cosmetic

`DataCenterProduction.tier` (1–4) and `redundancy` (N, N+1, 2N, 2N+1) are
**labels only** — they do not drive capex, opex, PUE, or availability.

- **Where:** `infrastructure/schema.py::DataCenterProduction`,
  `infrastructure/engines/production.py::_datacenter`.
- **Why:** the cost/availability impact of tier/redundancy is highly
  site-specific; rather than bake in an opinionated multiplier, the model lets
  the user set capex/PUE/availability directly. The labels document intent.
- **Implication:** changing tier/redundancy alone does not change any number.
- **Future refinement:** optional tier→PUE/availability/capex multipliers.

## Datacenter OPEX basis = facility MW; SLA revenue basis = IT MW (P3-4)

Fixed O&M and cooling/insurance scale with the **facility MW** (`it_capacity_mw
× PUE`), while SLA / colocation **revenue** is billed per sellable **IT MW**.

- **Where:** `production.py::_datacenter` (surfaces `capacity_mw` = facility MW
  and `capacity_mw_it` = IT MW), `engines/opex.py`, `engines/revenue.py` (SLA).
- **Why:** operating cost and cooling load track total facility power draw (the
  standard data-centre cost driver); revenue tracks sellable IT capacity. The
  PUE asymmetry between the two is intentional — a higher PUE means more cooling
  overhead per sellable IT-MW.
- **Implication:** the two bases differ by PUE by design; not a bug.
- **Pinned by:** `tests/unit/test_infra_opex.py::test_datacenter_fixed_om_keys_off_facility_mw`.

## H2 LCOE labeling

For green hydrogen the LCOE-style metric is computed and labeled as an "LCOE"
(levelized cost of energy) even though hydrogen output is mass (kg), so it is
effectively an **LCOH** (levelized cost of hydrogen) when the denominator is
production in energy-equivalent terms.

- **Where:** `infrastructure/model.py::_compute_kpis` (`compute_lcoe`).
- **Why:** the engine shares one levelized-cost helper across technologies; the
  number is meaningful (total discounted cost / total output) but the **label**
  is generic.
- **Implication:** read the H2 "LCOE" as a levelized unit cost; the unit follows
  the production denominator.
- **Future refinement:** a per-technology unit label (LCOE / LCOH / LCOS).

## Terminal value default = NONE for finite-life assets (P0-3)

Solar, wind, BESS and datacenter (finite-life) assets use **no terminal value**
(TV = 0) by default in the project EV / NPV. A Gordon-growth perpetuity or an
exit multiple is available only when explicitly requested.

- **Where:** `infrastructure/model.py` (`terminal_method` default "none"),
  `core/valuation.py::compute_dcf`.
- **Why:** a perpetuity on a finite-life asset overstates value (it was adding
  spurious terminal value, e.g. distorting the datacenter EV). Conservative
  default; explicit opt-in for salvage/exit.
- **Implication:** EV reflects only the modeled operating horizon unless the
  user adds a salvage/exit value.

## Business valuation FCF is UNLEVERED (P0-4)

`BusinessModel` values the enterprise on **unlevered FCF**
(EBIT·(1−t) + D&A − capex ± ΔWC), discounted at the WACC. A separate equity NPV
uses the full levered cash flow (including debt drawdown/principal) discounted at
the cost of equity.

- **Where:** `assets/business/model.py`.
- **Why:** mixing levered CFO (net of interest) with an EV discount rate while
  dropping the debt principal understated EV and was internally inconsistent.
  Unlevered FCF → WACC for EV is the textbook treatment and is coherent with the
  infra path.
- **Implication:** EV is capital-structure-neutral; leverage shows up in the
  equity NPV / IRR, not the EV.

## Real estate has a residual (sale) value (P0-7)

Real-estate models include a **residual / sale value** of the building at the
end of the horizon (unlike the finite-life infra default of TV = 0).

- **Where:** `assets/business/model.py` / real-estate preset
  (`real_estate_rental`).
- **Why:** a building depreciated over 30 years with only operating FCF never
  recovers its capital, making the NPV structurally (and unrealistically)
  negative. Real estate genuinely retains a market/residual value, so it is the
  documented exception to the "no terminal value" rule.
- **Implication:** the real-estate NPV includes an end-of-horizon asset value;
  finite-life energy assets do not (by default).

## Debt is deferred to COD (not capitalized as IDC)

During construction, debt is **drawn at financial close** but amortization is
**deferred to COD** on the **face** principal; the construction-phase interest
is assumed funded outside the debt balance (equity / a dedicated IDC reserve),
so the balance is **not** grossed up.

- **Where:** `core/drivers.py::AmortizationSchedule` (`deferral_periods` branch),
  `infrastructure/model.py::_compute_debt`, `HybridProject._tranche_debt_service`.
- **Why:** this `deferral` treatment (no IDC roll-up) is what reconciles with the
  validated hybrid consolidated Excel (sub-DSCR over the operating years). The alternative —
  capitalizing interest into the balance (`idc_periods`) — is supported in the
  schedule but is **not** the default path used by the deals.
- **Implication:** the modeled debt balance equals the face principal at COD;
  construction interest is an equity/reserve use, not added to debt.

## Amortization convention is ANNUAL for tranche debt service (P3-1)

The per-tranche debt-service series used for DSCR/MOIC is built on the **annual**
amortization convention (one amortization row per year, spread evenly across the
periods of each year) in **both** the standalone infra path and the
consolidated/hybrid consolidated hybrid path.

- **Where:** `infrastructure/model.py::_debt_service_series`,
  `hybrid/model.py::_tranche_debt_service`.
- **Why:** previously the standalone path amortized monthly, giving the **same
  loan** a ~1–3% different total service than the hybrid path — an
  inconsistency. Annual tranche service is standard and adequate for project
  finance, so both paths now agree exactly for the same loan.
- **Implication:** DSCR/MOIC for a given loan are identical whether the asset is
  run standalone or inside a hybrid/portfolio.
- **Pinned by:** `tests/unit/test_amortization_convention.py`.
- **Note:** the P&L / cash-flow interest and principal (accounting view) remain
  `DebtEngine`-driven on the period grid; this decision concerns the tranche
  **service** series feeding the DSCR/MOIC waterfall.
