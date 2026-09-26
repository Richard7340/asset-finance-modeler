"""Una ruta que no existe sugiere las buenas (27-sep): un agente puso la
degradacion bajo losses y bajo production seis veces seguidas."""
import pytest
from fastapi import HTTPException

from asset_finance_modeler.web_api.assets import _run_model


@pytest.mark.parametrize("mala,buena", [
    ("losses.degradation", "degradation.annual_rate"),
    ("production.degradation_annual_rate", "degradation.annual_rate"),
    ("opex.lines", "opex.other_lines"),
])
def test_sugiere_la_ruta_buena(mala, buena):
    with pytest.raises(HTTPException) as e:
        _run_model("solar_pv_50mw_spain", {mala: 1})
    assert buena in e.value.detail
