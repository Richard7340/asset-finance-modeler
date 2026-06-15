from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import CapexEvent


def test_repowering_restores_capacity_and_adds_capex():
    # bess_20mw_4h has cycle_based degradation configured, so a reset is observable.
    base = InfrastructureModel(load_preset("bess_20mw_4h")).run()

    cfg = load_preset("bess_20mw_4h")
    ppy = 12  # monthly preset
    cfg.capex_events = [
        CapexEvent(year=15, amount=5_000_000.0, resets_degradation=True, label="repowering")
    ]
    rep = InfrastructureModel(cfg).run()

    # (a) total capex up by the injection
    assert rep.summary["total_capex"] > base.summary["total_capex"]
    assert (
        abs(
            (rep.summary["total_capex"] - base.summary["total_capex"]) - 5_000_000.0
        )
        < 1.0
    )

    # (a') the injection shows up in investing cash flow at the event period
    event_period = 15 * ppy
    assert rep.cashflow["cfi"][event_period] < base.cashflow["cfi"][event_period]

    # (b) post-repowering output higher than the degraded base case
    late = 18 * ppy  # well after the year-15 reset
    base_rev = base.pnl["revenue"]
    rep_rev = rep.pnl["revenue"]
    assert rep_rev[late] > base_rev[late]


def test_capex_event_is_depreciated():
    # P1-5: the year-15 €846k repowering in svj_bess_cordoba must be depreciated,
    # so total book depreciation ~= total_capex (including the event), not just
    # the original capex.
    out = InfrastructureModel(load_preset("svj_bess_cordoba")).run()
    total_capex = out.summary["total_capex"]
    book_dep_total = sum(out.pnl["depreciation"])
    # Fully expensed within the 30-year horizon (event depreciated from yr15).
    assert abs(book_dep_total - total_capex) < 1.0


def test_capex_event_depreciation_starts_at_event_year():
    # The event's depreciation only begins from its event period, not period 0.
    base = InfrastructureModel(load_preset("bess_20mw_4h")).run()

    cfg = load_preset("bess_20mw_4h")
    ppy = 12
    cfg.capex_events = [
        CapexEvent(year=15, amount=3_000_000.0, resets_degradation=False, label="augmentation")
    ]
    rep = InfrastructureModel(cfg).run()

    base_dep = base.pnl["depreciation"]
    rep_dep = rep.pnl["depreciation"]
    event_period = 15 * ppy
    # No extra depreciation before the event period.
    assert abs(rep_dep[event_period - 1] - base_dep[event_period - 1]) < 1.0
    # Extra depreciation from the event period onward.
    assert rep_dep[event_period] > base_dep[event_period]
    # The €3M event is fully expensed within the horizon.
    assert abs((sum(rep_dep) - sum(base_dep)) - 3_000_000.0) < 1.0


def test_empty_capex_events_is_identity():
    base = InfrastructureModel(load_preset("bess_20mw_4h")).run()

    cfg = load_preset("bess_20mw_4h")
    cfg.capex_events = []
    same = InfrastructureModel(cfg).run()

    assert same.summary["total_capex"] == base.summary["total_capex"]
    assert same.pnl["revenue"] == base.pnl["revenue"]
    assert same.cashflow["cfi"] == base.cashflow["cfi"]
