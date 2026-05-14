import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import OpexConfig, TeamRole


def test_team_role_headcount_constant():
    r = TeamRole(role="founder", monthly_cost=4000, headcount=3)
    assert r.headcount_at_period(0) == 3
    assert r.headcount_at_period(100) == 3


def test_team_role_headcount_schedule():
    r = TeamRole(role="engineer", monthly_cost=5500, headcount_schedule=[0, 0, 1, 1, 2])
    assert r.headcount_at_period(0) == 0
    assert r.headcount_at_period(2) == 1
    assert r.headcount_at_period(4) == 2
    assert r.headcount_at_period(99) == 2


def test_team_role_start_period():
    r = TeamRole(role="marketing", monthly_cost=3000, headcount=1, start_period=6)
    assert r.headcount_at_period(5) == 0
    assert r.headcount_at_period(6) == 1


def test_team_role_end_period():
    r = TeamRole(role="contractor", monthly_cost=4500, headcount=1, end_period=12)
    assert r.headcount_at_period(11) == 1
    assert r.headcount_at_period(12) == 0


def test_team_role_both_fields_rejected():
    with pytest.raises(ValidationError):
        TeamRole(role="x", monthly_cost=1000, headcount=2, headcount_schedule=[1, 1])


def test_team_role_neither_field_rejected():
    with pytest.raises(ValidationError):
        TeamRole(role="x", monthly_cost=1000)


def test_opex_defaults():
    o = OpexConfig(team=[TeamRole(role="founder", monthly_cost=4000, headcount=1)])
    assert o.infra_fixed_eur == 0
    assert o.marketing_eur == 0
