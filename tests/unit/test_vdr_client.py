import asyncio
import json

import pytest

from asset_finance_modeler.intelligence.vdr_client import VDRClient


class TestVDRClient:
    def test_not_configured_by_default(self):
        client = VDRClient(token="")
        assert not client.is_configured

    def test_configured_with_token(self):
        client = VDRClient(token="test-token")
        assert client.is_configured

    def test_upload_without_token(self):
        client = VDRClient(token="")
        result = asyncio.run(client.upload("ws1", "test.json", '{"data": 1}'))
        assert result["ok"] is False
        assert "not configured" in result["error"]

    def test_download_without_token(self):
        client = VDRClient(token="")
        result = asyncio.run(client.download("ws1", "test.json"))
        assert result["ok"] is False

    def test_list_without_token(self):
        client = VDRClient(token="")
        result = asyncio.run(client.list_files("ws1"))
        assert result["ok"] is False

    def test_export_report_json(self):
        client = VDRClient()
        report = client.export_report_json({"name": "Test", "results": {"irr": 0.12}})
        data = json.loads(report)
        assert data["type"] == "gestnova-financial-report"
        assert data["scenario"]["name"] == "Test"

    def test_export_report_markdown(self):
        client = VDRClient()
        md = client.export_report_markdown(
            {"name": "Solar 50MW", "results": {"irr": 0.1234, "npv": 1500000}},
            {"name": "Proyecto Alpha", "technology": "Solar PV", "capacity_mw": 50},
        )
        assert "Financial Report" in md
        assert "Solar 50MW" in md
        assert "Proyecto Alpha" in md
        assert "50" in md
