import csv
import json

import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
from asset_finance_modeler.store.exports import to_csv, to_json


@pytest.fixture(scope="module")
def results():
    return SaasModel(load_preset("gestnova")).run()


def test_to_csv_pnl(results, tmp_path):
    out = tmp_path / "pnl.csv"
    to_csv(results, view="pnl", path=str(out))
    assert out.exists()
    with out.open() as f:
        rows = list(csv.reader(f))
    # header + 60 data rows
    assert len(rows) == 61
    assert "revenue" in rows[0]
    assert "period" == rows[0][0]


def test_to_csv_invalid_view(results, tmp_path):
    with pytest.raises(ValueError):
        to_csv(results, view="invalid", path=str(tmp_path / "x.csv"))


def test_to_json_full(results):
    payload = to_json(results)
    parsed = json.loads(payload)
    assert "summary" in parsed
    assert "pnl" in parsed
    assert "cashflow" in parsed
    assert isinstance(parsed["pnl"]["revenue"], list)
    assert len(parsed["pnl"]["revenue"]) == 60


def test_to_json_writes_to_path(results, tmp_path):
    out = tmp_path / "results.json"
    to_json(results, path=str(out))
    assert out.exists()
    parsed = json.loads(out.read_text())
    assert "summary" in parsed
