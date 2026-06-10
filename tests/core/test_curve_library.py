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
