import math

import pytest

from asset_finance_modeler.core.statements import compute_debt_metrics


def test_dscr():
    m = compute_debt_metrics(
        ebitda=[500, 500],
        ebit=[400, 400],
        interest_expense=[50, 50],
        principal_repaid=[100, 100],
        debt_outstanding=[1000, 900],
    )
    assert m["dscr"][0] == pytest.approx(500 / 150)
    assert m["icr"][0] == pytest.approx(8)
    assert m["leverage"][0] == pytest.approx(2)


def test_dscr_no_debt_service_returns_inf():
    m = compute_debt_metrics(
        ebitda=[100],
        ebit=[100],
        interest_expense=[0],
        principal_repaid=[0],
        debt_outstanding=[0],
    )
    assert m["dscr"][0] == math.inf
    assert m["icr"][0] == math.inf
    assert m["leverage"][0] == 0
