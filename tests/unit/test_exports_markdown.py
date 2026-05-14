import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
from asset_finance_modeler.store.exports import (
    to_markdown_report,
    to_markdown_table,
    to_summary,
)


@pytest.fixture(scope="module")
def results():
    cfg = load_preset("gestnova")
    return SaasModel(cfg).run()


def test_to_summary(results):
    summary = to_summary(results)
    assert "revenue_y1" in summary
    assert "enterprise_value" in summary
    assert isinstance(summary["revenue_y1"], (int, float))


def test_to_markdown_table_pnl(results):
    md = to_markdown_table(results, view="pnl", max_periods=6)
    assert "| period |" in md.lower() or "| Period |" in md
    assert "revenue" in md.lower()
    # Should contain at most 6 data rows
    data_lines = [line for line in md.split("\n") if line.startswith("| ") and "---" not in line]
    # 1 header + up to 6 data rows
    assert 1 <= len(data_lines) <= 7


def test_to_markdown_table_invalid_view(results):
    with pytest.raises(ValueError):
        to_markdown_table(results, view="nonexistent")


def test_to_markdown_report(results):
    report = to_markdown_report(results)
    assert "# " in report
    assert "Revenue" in report or "revenue" in report
    # Has at least 3 sections
    assert report.count("\n## ") >= 2
