import pytest

from asset_finance_modeler.core.drivers import (
    AmortizationSchedule,
    GrowthCurve,
    expand_growth,
)


def test_constant_value_expands():
    assert expand_growth(5.0, periods=4) == [5.0, 5.0, 5.0, 5.0]


def test_list_value_passes_through():
    assert expand_growth([1.0, 2.0, 3.0], periods=3) == [1.0, 2.0, 3.0]


def test_list_value_shorter_pads_with_last():
    assert expand_growth([1.0, 2.0], periods=4) == [1.0, 2.0, 2.0, 2.0]


def test_list_value_longer_than_periods_raises():
    with pytest.raises(ValueError):
        expand_growth([1.0, 2.0, 3.0, 4.0], periods=3)


def test_growth_curve_linear():
    c = GrowthCurve(kind="linear", start=10, end=20, periods=5)
    assert c.values() == [10.0, 12.5, 15.0, 17.5, 20.0]


def test_growth_curve_geometric():
    c = GrowthCurve(kind="geometric", start=10, rate=0.10, periods=4)
    vals = c.values()
    assert vals[0] == 10
    assert vals[1] == pytest.approx(11.0)
    assert vals[3] == pytest.approx(13.31)


def test_growth_curve_step():
    c = GrowthCurve(kind="step", values=[0, 0, 5, 10, 10], periods=5)
    assert c.values() == [0.0, 0.0, 5.0, 10.0, 10.0]


from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


def test_phased_curve_year1_is_base():
    """Year 1 (index 0) is the base, no growth applied yet."""
    vals = build_phased_curve(82.0, [CurvePhase(7, 0.02)], periods=10)
    assert vals[0] == 82.0


def test_phased_curve_n_years_yields_n_compounding_steps():
    """A '7y +2%' phase produces 7 compounding steps: values[7] == base * 1.02**7.

    Convention: growth steps INTO each year of the phase, so after a phase
    declared 'N years at +g%' the value reaches base * (1+g)**N at index N
    (FIX 2 — previously this was off by one and only gave 6 steps)."""
    base = 82.0
    vals = build_phased_curve(base, [CurvePhase(7, 0.02), CurvePhase(8, 0.0)], periods=16)
    assert vals[7] == pytest.approx(base * 1.02 ** 7)
    # Flat phase: value holds after the +2% phase ends.
    assert vals[8] == pytest.approx(base * 1.02 ** 7)
    assert vals[15] == pytest.approx(base * 1.02 ** 7)


def test_phased_curve_matches_spread_da_es_library():
    """The spread_da_es library curve reaches base*1.02**7 at the end of its
    '7y +2%' phase (index 7)."""
    from asset_finance_modeler.core.curve_library import load_curve

    c = load_curve("spread_da_es")
    vals = c.to_list(30)
    assert vals[0] == pytest.approx(82.0)
    assert vals[7] == pytest.approx(82.0 * 1.02 ** 7)


# ---------------------------------------------------------------------------
# IDC capitalization + COD-aligned amortization (project finance)
# ---------------------------------------------------------------------------


def test_idc_zero_is_identical_to_no_idc():
    """idc_periods=0 → schedule is byte-identical to the legacy schedule (no
    regression for assets with no construction timeline)."""
    base = AmortizationSchedule(
        principal=1_000_000.0, annual_rate=0.05, term_periods=10,
        periods_per_year=1, kind="french",
    ).rows()
    idc0 = AmortizationSchedule(
        principal=1_000_000.0, annual_rate=0.05, term_periods=10,
        periods_per_year=1, kind="french", idc_periods=0,
    ).rows()
    assert idc0 == base


def test_idc_capitalizes_interest_during_construction():
    """With idc_periods>0: construction periods carry NO debt service (interest
    capitalized into the balance), then amortization runs on the grossed-up
    balance starting at COD."""
    principal = 1_000_000.0
    rate = 0.10
    idc = 2
    rows = AmortizationSchedule(
        principal=principal, annual_rate=rate, term_periods=10,
        periods_per_year=1, kind="french", idc_periods=idc,
    ).rows()
    # First `idc` rows are construction: no payment at all (IDC capitalized).
    for t in range(idc):
        assert rows[t]["total_payment"] == 0.0
        assert rows[t]["principal_payment"] == 0.0
        assert rows[t]["interest"] == 0.0
    # Balance at COD = principal grossed up by capitalized interest.
    expected_cod_balance = principal * (1 + rate) ** idc
    assert rows[idc]["balance_start"] == pytest.approx(expected_cod_balance)
    # The amortized rows (from COD) repay the grossed-up balance fully.
    amort_rows = rows[idc:]
    assert len(amort_rows) == 10
    assert amort_rows[-1]["balance_end"] == pytest.approx(0.0, abs=1e-6)
    # Total principal repaid == grossed-up balance (IDC is recovered).
    total_principal = sum(r["principal_payment"] for r in amort_rows)
    assert total_principal == pytest.approx(expected_cod_balance)


def test_deferral_defers_amortization_on_face_value():
    """deferral_periods: no debt service during construction, then the FACE
    principal (NOT grossed up) amortizes over the tenor from COD."""
    principal = 1_000_000.0
    rate = 0.10
    defer = 2
    rows = AmortizationSchedule(
        principal=principal, annual_rate=rate, term_periods=10,
        periods_per_year=1, kind="french", deferral_periods=defer,
    ).rows()
    for t in range(defer):
        assert rows[t]["total_payment"] == 0.0
        assert rows[t]["balance_end"] == principal  # NOT grossed up
    # Amortization starts at COD on the FACE principal.
    assert rows[defer]["balance_start"] == pytest.approx(principal)
    amort_rows = rows[defer:]
    assert len(amort_rows) == 10
    total_principal = sum(r["principal_payment"] for r in amort_rows)
    assert total_principal == pytest.approx(principal)


def test_deferral_zero_is_identical_to_no_deferral():
    """deferral_periods=0 → byte-identical to the legacy schedule."""
    base = AmortizationSchedule(
        principal=500_000.0, annual_rate=0.06, term_periods=8,
        periods_per_year=1, kind="linear",
    ).rows()
    d0 = AmortizationSchedule(
        principal=500_000.0, annual_rate=0.06, term_periods=8,
        periods_per_year=1, kind="linear", deferral_periods=0,
    ).rows()
    assert d0 == base
