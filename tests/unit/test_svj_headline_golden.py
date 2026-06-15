"""SVJ headline golden + structural invariants (FIX 6).

Locks the post-fix SVJ economics so silent drift is caught:

- The exact headline KPIs from ``run_svj({})`` (tight tolerances).
- The bridge identity: hybrid NPV == FV leg + BESS leg (no terminal value,
  no synergy) — neither unlevered leg embeds a Gordon perpetuity.
- The DSCR waterfall is net-of-senior: with hand numbers, the subordinated
  DSCR equals (CFADS - senior_DS) / sub_DS.

Post-fix actuals (after FIX 1 DoD/RTE + FIX 2 phased-curve off-by-one):
  npv_fv      = -716,461
  npv_bess    = +1,673,210
  npv_hybrid  = +956,749
  revenue_y1  = 851,952
  dscr_sub_min= 0.94
  moic_sub    = 1.368

P1 UPDATE (timeline + capex-event depreciation):
  npv_fv      = -924,669   (P1-4: FV revenue deferred 29mo to COD)
  npv_bess    = +1,842,952 (P1-4 deferral 11mo + P1-5 repowering tax shield)
  npv_hybrid  = +918,282
  revenue_y1  = 554,418    (P1-4: calendar yr1 is mostly construction — FV=0,
                            BESS partial; first OPERATING year is higher)
  dscr_sub_min= 0.48       (P1-4: BESS COD 11mo defers cashflow vs the 7yr sub
                            tenor that still starts at close — sub DSCR drops)
  moic_sub    = 1.368      (unchanged — sub debt service is timeline-independent)

DEBT-COD ALIGNMENT (this fix): the construction-period DSCR was an artifact —
debt amortized from financial close while P1 deferred revenue to COD. Standard
project finance defers debt service to COD (construction interest funded by
equity / an IDC reserve — face-value deferral, NOT IDC capitalization, which
reconciles with the validated Excel) and measures DSCR over OPERATING periods
only. Project COD = max(FV 29mo, BESS 11mo) -> 2 annual periods.
  dscr_sub_min   = 0.87  (was 0.48 — the two no-/partial-revenue construction
                          years no longer score a DSCR; min is now a genuine
                          operating-period figure; the first FULL operating
                          years are ~1.20 / 1.11, in the Excel's ~1.14-1.31 band)
  dscr_senior_min= 2.07  (was 1.65 — construction years no longer drag it down;
                          back near the pre-P1 2.06)
  recovery       = 3.76  (was 4.0 — the going-concern recovery window starts at
                          COD + sub tenor, deferred 2 years)
  irr            = 0.0587(hybrid IRR is on consolidated unlevered FCF; the tiny
                          move is rounding, not a debt-timing effect)
  npv_*/capex/moic/revenue_y1 unchanged (NPV is unlevered; MOIC is debt-service-
                          shape independent; capex/revenue untouched).
"""

from asset_finance_modeler.core.financing import compute_waterfall_dscr
from asset_finance_modeler.core.portfolio import consolidate_npv
from asset_finance_modeler.deals.svj import run_svj


def test_svj_headline_golden() -> None:
    """Pin the exact post-fix headline KPIs (±1 EUR / tight on ratios)."""
    k = run_svj({})["kpis"]
    # P1 GOLDEN (timeline deferral P1-4 + capex-event depreciation P1-5).
    assert abs(k["npv_fv"] - (-924_669)) <= 1
    assert abs(k["npv_bess"] - 1_842_952) <= 1
    assert abs(k["npv_hybrid"] - 918_282) <= 1
    assert abs(k["revenue_y1"] - 554_418) <= 1
    # Debt-COD alignment: DSCR over operating periods only (debt deferred to
    # COD). sub-DSCR min back to a sensible operating range; senior recovers.
    assert abs(k["dscr_sub_min"] - 0.87) <= 0.01
    assert abs(k["dscr_senior_min"] - 2.07) <= 0.01
    assert abs(k["moic_sub"] - 1.368) <= 0.001
    assert abs(k["total_capex"] - 7_269_533) <= 1


def test_bridge_is_sum_of_unlevered_legs_no_terminal_value() -> None:
    """Hybrid NPV is exactly FV leg + BESS leg — an additive bridge with no
    perpetuity terminal value and no synergy add-on."""
    r = run_svj({})
    b = r["bridge"]
    k = r["kpis"]
    # Bridge == sum of legs (±1 EUR: hybrid is round(unrounded_fv +
    # unrounded_bess) while the legs are rounded independently, so summing the
    # rounded legs can differ by a euro — additive, no-synergy invariant holds).
    assert abs(b["hybrid"] - (b["fv"] + b["bess"])) <= 1
    # Bridge legs == headline NPVs (same unlevered convention).
    assert b["fv"] == k["npv_fv"]
    assert b["bess"] == k["npv_bess"]
    assert b["hybrid"] == k["npv_hybrid"]

    # No terminal value: the legs are plain discounted FCF sums. consolidate_npv
    # discounts a finite annual FCF series with NO perpetuity tail, so a leg's
    # magnitude stays bounded by the (small) sum of annual FCFs / discount — a
    # Gordon TV on these assets would balloon the figure into the tens of
    # millions. Assert each leg is within a no-TV order of magnitude.
    assert abs(k["npv_fv"]) < 5_000_000
    assert abs(k["npv_bess"]) < 5_000_000


def test_consolidate_npv_has_no_perpetuity_tail() -> None:
    """consolidate_npv is a plain discounted sum — adding a far-future zero year
    must NOT change the result (a Gordon TV would have been appended)."""
    fcf = [100.0, 100.0, 100.0]
    npv3 = consolidate_npv(fcf, 0.10)
    npv4 = consolidate_npv(fcf + [0.0], 0.10)
    assert npv4 == npv3  # no terminal value tacked on


def test_dscr_waterfall_is_net_of_senior_hand_numbers() -> None:
    """Sub DSCR uses CFADS net of senior service: (CFADS - senior_DS)/sub_DS."""
    cfads = [1_000.0, 1_000.0]
    senior_ds = [400.0, 400.0]
    sub_ds = [200.0, 200.0]
    dscrs = compute_waterfall_dscr(cfads, [senior_ds, sub_ds])

    # Senior DSCR = CFADS / senior_DS.
    assert dscrs[0][0] == 1_000.0 / 400.0
    # Subordinated DSCR = (CFADS - senior_DS) / sub_DS = (1000-400)/200 = 3.0.
    assert dscrs[1][0] == (1_000.0 - 400.0) / 200.0
    assert dscrs[1][0] == 3.0
