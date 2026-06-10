from asset_finance_modeler.core.capex_events import (
    apply_capex_events,
    apply_degradation_resets,
)


def test_apply_capex_events_adds_amount_at_period():
    spend = [1000.0] + [0.0] * 29
    out = apply_capex_events(spend, events=[(15, 200.0)], periods_per_year=1)
    assert out[0] == 1000.0
    assert out[15] == 200.0
    assert sum(out) == 1200.0
    assert spend[15] == 0.0


def test_apply_capex_events_monthly_ppy():
    spend = [0.0] * 360
    out = apply_capex_events(spend, events=[(15, 500.0)], periods_per_year=12)
    assert out[180] == 500.0


def test_apply_degradation_resets_restores_capacity():
    base = [1.0 - 0.02 * t for t in range(30)]
    out = apply_degradation_resets(base, reset_periods=[15])
    assert out[14] == base[14]
    assert out[15] == base[0]
    assert out[16] == base[1]
    assert out[29] == base[29 - 15]
    assert base[15] == 1.0 - 0.30      # input not mutated


def test_apply_degradation_resets_empty_is_identity():
    base = [1.0, 0.9, 0.8]
    assert apply_degradation_resets(base, reset_periods=[]) == base
