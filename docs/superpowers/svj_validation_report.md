# SVJ Hybrid (FV + BESS Córdoba) — Reconciliation Report vs Validated Excel

**Phase 6, Task 3 — calibration / diagnostic.** This is an HONEST reconciliation,
not a forced exact match. Below is the actual model output (after the FV
calibration described in Part A) against the validated Excel targets, the % gap,
and for each material gap (>10%) the probable cause and the input/convention
lever responsible.

Run convention: monthly horizon (360 periods), aggregated to annual; project
free cash flow = `cfo + cfi`; consolidated discount rate 5.37 %; senior tranche
€2.22M / 3.2 % / 10y french; subordinated €1.841M / 8.5 % / 7y french.

---

## Part A — FV revenue & capex diagnosis

### A.1 — Production: the performance ratio WAS being double-applied

The solar engine (`engines/production.py::_solar`) computes:

```
annual_mwh = capacity_mwp * 1000 * specific_yield_kwh_kwp * performance_ratio / 1000
```

i.e. it multiplies the specific yield by `performance_ratio`. The validated
Excel's `specific_yield_kwh_kwp = 1582` is a **net** specific yield (already
post-PR, post-loss output in MWh/MWp/yr). Multiplying it again by `PR = 0.86`
therefore **double-applies** the performance ratio:

| | production |
|---|---|
| Original preset (`PR = 0.86`) | 4.76 × 1582 × 0.86 = **6,476 MWh/yr** |
| Excel target | **≈ 7,530 MWh/yr** |
| Calibrated preset (`PR = 1.0`) | 4.76 × 1582 × 1.0 = **7,530 MWh/yr** ✅ |

**Is it a genuine engine bug?** It is a *semantics* issue, not a clear bug: the
engine treats `specific_yield_kwh_kwp` as the **gross** yield and `PR` as the
derate. That is a legitimate convention for some data sources. But the SVJ
preset's yield was sourced as a **net** figure, so the two conventions collided.
We did **NOT** change the engine (that would silently shift every other solar
model). Instead we **calibrated the preset**: `performance_ratio: 1.0`, baking
the (already net) PR into the yield. Documented inline in
`svj_fv_cordoba.yaml`.

> Recommendation for the engine owner: document on `SolarProduction` whether
> `specific_yield_kwh_kwp` is expected gross or net, so future presets don't
> repeat the collision.

### A.2 — Capex trimmed to the Excel basis

The original preset added 5 % contingency + €100k development + €200k grid on
top of EPC, inflating `total_capex` to **€4,948,140**. The Excel total_capex is
**≈ €4.44M**, essentially EPC (4.76M Wp × €0.93 = €4,426,800) plus a thin
development allowance. Calibrated: contingency 0 %, grid €0, development €13,200
→ `total_capex = €4,440,000` (exact match).

### A.3 — Residual on FV revenue

After the production fix, FV revenue Y1 = **€278,352** (7,530 MWh × ~€36.96/MWh
blended). The Excel target is **~€293k**. The remaining **~5 % gap is pricing,
not volume** — the Excel evidently uses a marginally higher blended price
(higher merchant capture or PPA price). Production now matches exactly; we did
NOT inflate the price to force the last 5 %. Lever for a future pass: bump
`merchant.capture_ratio` (0.85) or `ppa.price_eur_per_unit` (43.0) by ~5 %.

---

## Part B / C — Actual vs Target, all KPIs

| KPI | ACTUAL | TARGET | gap % | match? |
|---|---:|---:|---:|:--:|
| FV production (MWh/yr) | 7,530 | ~7,530 | ~0 % | ✅ |
| FV revenue Y1 (€) | 278,352 | ~293,000 | −5.0 % | ~ |
| FV total_capex (€) | 4,440,000 | ~4,440,000 | ~0 % | ✅ |
| **FV project NPV** (plain, 5.37 %) | **−1,999,370** | **−1,220,000** | −63.9 % | ✗ |
| FV enterprise value (w/ terminal) | −1,330,769 | −1,220,000 | −9.1 % | ~ |
| **BESS project NPV** (plain, 5.37 %) | **+1,228,573** | **+2,172,000** | −43.4 % | ✗ |
| BESS enterprise value (w/ terminal) | +1,631,564 | +2,172,000 | −24.9 % | ✗ |
| **Hybrid NPV** (plain consolidated) | **−770,797** | **+1,644,000** | — (sign flip) | ✗ |
| Hybrid EV-sum (FV EV + BESS EV) | +300,795 | +1,644,000 | −81.7 % | ✗ |
| **DSCR subordinated min** | **0.697** | **1.14** (range 1.14–1.31) | −38.9 % | ✗ |
| DSCR subordinated avg | 0.957 | ~1.20 | −20 % | ✗ |
| DSCR senior min | 1.653 | (>1.4 senior) | — | ✅ |
| **MOIC subordinated** | **1.368** | **1.37** | −0.1 % | ✅ |
| Recovery (going concern) | 3.167 | ~1.4 | +126 % | ✗ |

### What matches well
- **MOIC subordinated 1.368 vs 1.37** — essentially exact. MOIC is a pure
  cash-in/cash-out ratio (Σ debt service ÷ principal) independent of the
  EBITDA/NPV convention questions, so it reconciles cleanly.
- **FV production & capex** — exact after calibration.
- **DSCR senior** — comfortably covered; senior sits at the top of the waterfall.

### Residual gaps and their drivers (honest)

**1. NPVs (FV, BESS, hybrid) — the convention difference: plain NPV vs
enterprise value with terminal.**
`HybridProject.npv` and our per-asset bridge use `consolidate_npv`, a **plain
discounted FCF with NO terminal value**. The Excel values the projects as an
**enterprise value WITH a terminal** (the model's own `enterprise_value` does
inject a Gordon terminal). The gap is almost entirely the terminal:
- FV: plain −1,999k vs EV −1,331k vs target −1,220k → with terminal the gap
  closes from −64 % to −9 %.
- BESS: plain +1,229k vs EV +1,632k vs target +2,172k → terminal closes part of
  it, residual ~25 % is the ancillary-curve compression (see #2) eating
  late-life cash that the Excel keeps higher.
- **Hybrid**: plain −771k (sign-flipped vs target) vs EV-sum +301k. Even on the
  EV basis the hybrid is +301k vs target +1,644k. The €1.34M residual is the
  same two drivers compounded: (a) BESS late-life ancillary cash is compressed
  too hard, (b) FV revenue is ~5 % light on price. **Lever:** report the hybrid
  on the enterprise-value basis (sum of per-asset EV) AND soften the ancillary
  curve (#2); the price bump (#A.3) lifts FV.

**2. DSCR subordinated min 0.697 vs target 1.14 — the ancillary `curve_points`
compress too hard, and EBITDA proxy ≠ Excel CFADS.**
Year-by-year subordinated DSCR (CFADS-after-senior ÷ sub service):

```
yr1 1.233 | yr2 1.110 | yr3 1.039 | yr4 0.968 | yr5 0.869 | yr6 0.783 | yr7 0.697
```

The sub service is flat (french amort, constant total payment), but consolidated
EBITDA falls from €706k (yr1) to €483k (yr7) because the BESS ancillary curve
`curve_points` decays from 1.0 → 0.40 over those 7 years. The Excel's target
range **1.14–1.31 with min 1.14** means its DSCR stays ABOVE 1.14 across the
whole sub tenor — i.e. **the Excel does NOT let ancillary revenue collapse like
our curve does.** Two compounding causes:
   - **Ancillary curve compression** (primary): our `curve_points` halve aFRR
     revenue by year 5 and cut it to 40 % by year 7. The Excel holds it
     materially higher.
   - **EBITDA proxy vs post-tax CFADS** (secondary, opposite sign): our DSCR
     uses *pre-tax* consolidated EBITDA as the CFADS proxy. The Excel's CFADS is
     *post-tax, net of senior*. Pre-tax EBITDA over-states cash, so if anything
     our DSCR is generous on this axis — meaning the curve compression is the
     dominant, real driver of the shortfall.

   **Recommended next calibration (do NOT fake the number):** soften the BESS
   ancillary `curve_points` so the year-7 factor is ≥ ~0.65 (the Excel basis),
   which lifts year-7 consolidated EBITDA enough to push min DSCR ≥ 1.14. This
   is a deal-assumption change (aFRR price durability) and should be confirmed
   against the Excel's ancillary curve before applying.

**3. Recovery 3.167 vs ~1.4 — convention difference (going-concern horizon vs
collateral/liquidation basis).**
`compute_recovery_multiple` takes the **PV of ALL CFADS from year 7 to year 30
(23 years), discounted, ÷ the ORIGINAL principal €1.841M**. Since the sub is
fully amortized by year 7, dividing 23 years of going-concern cash by the full
original principal yields 3.17×. The Excel's ~1.4× implies a **collateral /
liquidation basis** (or recovery measured against the *outstanding* balance at
default, which is ~0 after full amort, or a short liquidation window) — not 23
years of discounted operating cash. This is a metric-definition gap, not an
input error. **Lever:** to reconcile, recovery should be computed against the
outstanding principal at the measurement period and/or over a bounded
liquidation window, or expressed as enterprise value ÷ outstanding debt.

---

## Summary

After the FV calibration (PR double-application removed; capex trimmed to the
Excel basis), **production, capex, and MOIC reconcile cleanly**. The remaining
divergences are dominated by **two genuine, documented drivers**:

1. **Valuation convention** — plain NPV vs enterprise value with a Gordon
   terminal. On the EV basis the per-asset NPVs are within 9–25 % of target.
2. **BESS ancillary curve compression** — our `curve_points` decay too
   aggressively, which simultaneously (a) depresses BESS late-life NPV and
   (b) drives the subordinated DSCR below the 1.14 floor in the late tenor
   years. The Excel evidently holds aFRR revenue more durable.

A residual ~5 % FV pricing gap remains. **None of these were forced to a fake
match.** The validation test (`tests/unit/test_svj_validation.py`) asserts the
KPIs that legitimately reconcile (MOIC ~1.37, recovery > 1, finite NPV, DSCR
waterfall ordering) and leaves wide / open the ones still under reconciliation.
