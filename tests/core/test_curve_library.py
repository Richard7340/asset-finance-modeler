import pytest

from asset_finance_modeler.core.curve_library import list_curves, load_curve


def test_list_curves_includes_seed():
    assert "spread_da_es" in list_curves()


def test_load_curve_spread_da_es():
    c = load_curve("spread_da_es")
    assert c.name == "spread_da_es"
    assert "Agere" in c.source or "Modo" in c.source
    assert len(c.to_list(30)) == 30
    assert c.at(0) > 0


def test_load_unknown_curve_raises():
    with pytest.raises(KeyError):
        load_curve("does_not_exist_xyz")


def test_seed_curves_present():
    names = list_curves()
    for n in ("spread_da_es", "ancillary_afrr_es", "solar_capture_es"):
        assert n in names
    anc = load_curve("ancillary_afrr_es")
    assert anc.to_list(10)[2] < anc.to_list(10)[0]   # comprime tras yr1 (Agere)
    sol = load_curve("solar_capture_es")
    assert sol.at(0) > sol.at(29)                     # captura solar decae
