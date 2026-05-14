import pytest

from asset_finance_modeler.assets.saas.engines import COGSEngine, OpexEngine
from asset_finance_modeler.assets.saas.schema import (
    COGSConfig,
    LLMTier,
    OpexConfig,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    TeamRole,
)


def test_cogs_per_active_unit():
    cogs = COGSConfig(
        per_active_unit=PerActiveUnitCosts(
            llm_tokens=[LLMTier(
                model="sonnet-4-7",
                eur_per_million_input=3.0,
                eur_per_million_output=15.0,
                avg_tokens_in_per_month=1_000_000,
                avg_tokens_out_per_month=200_000,
            )],
            infra_eur=2.0,
        ),
        per_active_customer=PerActiveCustomerCosts(support_eur=15),
    )
    eng = COGSEngine(cogs, active_units=[2.0, 4.0], active_customers=[1.0, 2.0])
    out = eng.compute()
    assert out["total_cogs"][0] == pytest.approx(31.0)
    assert out["total_cogs"][1] == pytest.approx(62.0)


def test_opex_team_ramp():
    opex = OpexConfig(
        team=[
            TeamRole(role="founder", monthly_cost=4000, headcount=3),
            TeamRole(role="engineer", monthly_cost=5500, headcount_schedule=[0, 0, 1, 1, 2]),
        ],
        infra_fixed_eur=1200,
        marketing_eur=2000,
    )
    eng = OpexEngine(opex, periods=5)
    out = eng.compute()
    assert out["total_opex"][0] == pytest.approx(15200.0)
    assert out["total_opex"][2] == pytest.approx(20700.0)
    assert out["total_opex"][4] == pytest.approx(26200.0)
    assert out["team_cost"][2] == pytest.approx(17500.0)
