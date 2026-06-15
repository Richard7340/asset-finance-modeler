"""P3-1: the standalone infrastructure debt-service series and the hybrid/SVJ
tranche debt-service must use the SAME amortization convention, so the SAME
loan gives the SAME annual debt service in both paths.

Before P3-1 the standalone infra path amortized MONTHLY (periods_per_year=12,
term=tenor*12) while the hybrid/SVJ path amortizes ANNUALLY (periods_per_year=1,
term=tenor). For a 5y/8.5% loan that is a ~3% difference in total service for
the same loan — an inconsistency. We unify on the ANNUAL convention (fine for
project finance): the infra per-tranche service is built annually and spread
evenly across the periods of each year, so its annual buckets equal the hybrid
tranche service exactly.
"""

from __future__ import annotations

import pytest

from asset_finance_modeler.assets.hybrid.model import HybridProject, TrancheSpec
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def _annual_buckets(series: list[float], ppy: int) -> list[float]:
    return [sum(series[y * ppy : (y + 1) * ppy]) for y in range(len(series) // ppy)]


@pytest.mark.parametrize(
    ("principal", "rate", "tenor", "amort"),
    [
        (1_000_000.0, 0.085, 5, "french"),
        (2_220_000.0, 0.032, 10, "french"),
        (5_000_000.0, 0.06, 8, "linear"),
        (3_000_000.0, 0.05, 7, "bullet"),
    ],
)
def test_standalone_and_hybrid_tranche_service_match(principal, rate, tenor, amort):
    ppy = 12
    horizon_years = tenor + 2
    n = horizon_years * ppy

    # Standalone infra per-tranche service (now annual convention, spread to ppy).
    infra_ds = InfrastructureModel._debt_service_series(
        principal=principal,
        annual_rate=rate,
        term_periods=tenor * ppy,
        grace_periods=0,
        amortization=amort,
        drawdown_period=0,
        n=n,
        ppy=ppy,
        deferral_periods=0,
    )
    infra_annual = _annual_buckets(infra_ds, ppy)

    # Hybrid/SVJ tranche service (annual rows, one per year).
    spec = TrancheSpec(
        principal=principal, interest_rate=rate, tenor_years=tenor, amortization=amort
    )
    hybrid_ds = HybridProject._tranche_debt_service(spec, horizon_years, 0)

    assert len(infra_annual) == len(hybrid_ds)
    for y, (a, b) in enumerate(zip(infra_annual, hybrid_ds, strict=True)):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-6), f"year {y}: {a} != {b}"

    # And the TOTAL service over the loan matches (same loan -> same service).
    assert sum(infra_annual) == pytest.approx(sum(hybrid_ds), rel=1e-9)
