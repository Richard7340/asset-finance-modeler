"""E2E test: financial analysis -> VDR sharing -> workspace isolation.

Tasks 9 + 10 of Plan 6: integration tests covering the full flow from project
creation through VDR export, plus multi-tenant workspace isolation guarantees.
"""
import asyncio
import json
import sqlite3

import pytest

from asset_finance_modeler.intelligence.privacy import (
    anonymize_insight,
    should_collect_meta_learning,
)
from asset_finance_modeler.intelligence.vdr_client import VDRClient
from asset_finance_modeler.mcp_server.tools.vdr_sharing import (
    handle_explain_vdr,
    handle_share_to_vdr,
)
from asset_finance_modeler.store.projects import (
    Project,
    SQLiteProjectStore,
    new_project_id,
)
from asset_finance_modeler.store.workspace_settings import (
    WorkspaceSettings,
    WorkspaceSettingsStore,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Task 9 — E2E financial flow
# ---------------------------------------------------------------------------


class TestE2EFinancialFlow:
    """Test the complete flow: create project -> run scenario -> share to VDR -> privacy."""

    def test_project_creation_with_user_workspace(self, tmp_path):
        """User A creates a project scoped to their workspace."""
        store = SQLiteProjectStore(str(tmp_path / "test.db"))
        store.initialize()

        project = Project(
            id=new_project_id(),
            user_id="user-a",
            name="Solar 50MW Spain",
            workspace_id="ws-gestnova",
            asset_type="solar_pv",
            region="ES",
        )
        store.save(project)

        # Verify it was persisted
        loaded = store.get(project.id)
        assert loaded is not None
        assert loaded.name == "Solar 50MW Spain"
        assert loaded.workspace_id == "ws-gestnova"

        # Verify workspace-scoped listing
        projects = store.list_by_tenant(
            user_id="user-a", workspace_id="ws-gestnova"
        )
        assert len(projects) >= 1
        assert any(p.name == "Solar 50MW Spain" for p in projects)

    def test_share_to_vdr_without_token(self, monkeypatch):
        """Share generates local report when VDR token not configured."""
        monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)
        result = _run(
            handle_share_to_vdr(
                {
                    "scenario_id": "sc-test-123",
                    "format": "json",
                    "workspace_id": "ws-gestnova",
                }
            )
        )
        data = json.loads(result[0]["text"])
        assert data["ok"] is True
        assert data["status"] == "local_only"

    def test_vdr_client_export_formats(self):
        """VDR client can export as JSON and Markdown."""
        client = VDRClient()

        scenario = {
            "name": "Solar 50MW",
            "results": {"irr": 0.1234, "npv": 5_000_000},
        }
        project = {
            "name": "Proyecto Alpha",
            "technology": "Solar PV",
            "capacity_mw": 50,
        }

        # JSON export
        json_report = client.export_report_json(scenario, project)
        data = json.loads(json_report)
        assert data["type"] == "gestnova-financial-report"
        assert data["scenario"]["results"]["irr"] == 0.1234
        assert data["project"]["name"] == "Proyecto Alpha"

        # Markdown export
        md_report = client.export_report_markdown(scenario, project)
        assert "Solar 50MW" in md_report
        assert "Proyecto Alpha" in md_report
        assert "Solar PV" in md_report

    def test_meta_learning_privacy_flow(self):
        """Meta-learning respects privacy settings via WorkspaceSettingsStore."""
        conn = sqlite3.connect(":memory:")
        settings_store = WorkspaceSettingsStore(conn)

        # Default: meta-learning enabled
        assert should_collect_meta_learning("free", opt_out=False) is True

        # User opts out
        settings_store.set_opt_out("ws-test", True)
        settings = settings_store.get("ws-test")
        assert settings.meta_learning_enabled is False

        # Enterprise overrides opt-out
        settings_store.save(
            WorkspaceSettings(
                workspace_id="ws-enterprise",
                meta_learning_opt_out=True,
                tier="enterprise",
            )
        )
        assert settings_store.get("ws-enterprise").meta_learning_enabled is True

    def test_insight_anonymization(self):
        """Insights are properly anonymized before meta-learning collection."""
        raw = {
            "user_id": "user-a",
            "workspace_id": "ws-gestnova",
            "email": "riky@gestnova.eu",
            "scenario_id": "sc-123",
            "irr": 0.15,
            "technology": "solar",
        }
        clean = anonymize_insight(raw)

        # PII fields stripped
        assert "user_id" not in clean
        assert "workspace_id" not in clean
        assert "email" not in clean

        # Non-PII preserved
        assert clean["irr"] == 0.15
        assert clean["technology"] == "solar"

        # _id fields hashed (not plaintext)
        assert clean["scenario_id"] != "sc-123"
        assert len(clean["scenario_id"]) == 12

    def test_explain_vdr_suggests_flow(self):
        """explain_vdr returns a suggested analysis flow."""
        result = _run(
            handle_explain_vdr(
                {
                    "vdr_path": "financial-reports/solar-50mw.json",
                    "question": "What is the IRR?",
                }
            )
        )
        data = json.loads(result[0]["text"])
        assert data["ok"] is True
        assert "suggested_flow" in data
        assert len(data["suggested_flow"]) >= 2

    def test_full_e2e_project_to_vdr(self, tmp_path, monkeypatch):
        """End-to-end: create project -> build report -> anonymize -> share."""
        monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)

        # Step 1: Create project
        store = SQLiteProjectStore(str(tmp_path / "e2e.db"))
        store.initialize()
        project = Project(
            id=new_project_id(),
            user_id="user-a",
            name="Wind 100MW Portugal",
            workspace_id="ws-gestnova",
            asset_type="wind",
            region="PT",
        )
        store.save(project)

        # Step 2: Generate VDR report
        client = VDRClient()
        scenario_data = {"name": "Base Case", "results": {"irr": 0.0987, "npv": 12_000_000}}
        project_data = {"name": project.name, "technology": "Wind", "capacity_mw": 100}
        json_report = client.export_report_json(scenario_data, project_data)
        parsed = json.loads(json_report)
        assert parsed["type"] == "gestnova-financial-report"
        assert parsed["project"]["name"] == "Wind 100MW Portugal"

        # Step 3: Anonymize insights derived from this report
        insight = {
            "user_id": project.user_id,
            "workspace_id": project.workspace_id,
            "irr": parsed["scenario"]["results"]["irr"],
            "technology": "wind",
            "region": "PT",
        }
        clean = anonymize_insight(insight)
        assert "user_id" not in clean
        assert clean["irr"] == 0.0987
        assert clean["region"] == "PT"

        # Step 4: Share (local-only without token)
        result = _run(
            handle_share_to_vdr(
                {
                    "scenario_id": "sc-e2e",
                    "workspace_id": "ws-gestnova",
                    "format": "json",
                }
            )
        )
        data = json.loads(result[0]["text"])
        assert data["ok"] is True
        assert data["status"] == "local_only"


# ---------------------------------------------------------------------------
# Task 10 — Multi-tenant workspace isolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    """Verify workspace isolation across all stores."""

    def test_project_isolation_same_workspace(self, tmp_path):
        """Two users in same workspace see only their own projects."""
        store = SQLiteProjectStore(str(tmp_path / "test.db"))
        store.initialize()
        store.save(
            Project(
                id=new_project_id(),
                user_id="user-a",
                name="Project A",
                workspace_id="ws-shared",
            )
        )
        store.save(
            Project(
                id=new_project_id(),
                user_id="user-b",
                name="Project B",
                workspace_id="ws-shared",
            )
        )

        a_projects = store.list_by_tenant(user_id="user-a", workspace_id="ws-shared")
        b_projects = store.list_by_tenant(user_id="user-b", workspace_id="ws-shared")
        assert len(a_projects) == 1
        assert a_projects[0].name == "Project A"
        assert len(b_projects) == 1
        assert b_projects[0].name == "Project B"

    def test_project_isolation_different_workspaces(self, tmp_path):
        """Same user in different workspaces sees only workspace-scoped projects."""
        store = SQLiteProjectStore(str(tmp_path / "test.db"))
        store.initialize()
        store.save(
            Project(
                id=new_project_id(),
                user_id="user-a",
                name="Gestnova Project",
                workspace_id="ws-gestnova",
            )
        )
        store.save(
            Project(
                id=new_project_id(),
                user_id="user-a",
                name="Family Project",
                workspace_id="ws-family",
            )
        )

        gestnova = store.list_by_tenant(user_id="user-a", workspace_id="ws-gestnova")
        family = store.list_by_tenant(user_id="user-a", workspace_id="ws-family")

        assert len(gestnova) == 1
        assert gestnova[0].name == "Gestnova Project"
        assert len(family) == 1
        assert family[0].name == "Family Project"

    def test_workspace_settings_isolation(self):
        """Each workspace has independent settings."""
        conn = sqlite3.connect(":memory:")
        store = WorkspaceSettingsStore(conn)
        store.save(
            WorkspaceSettings(
                workspace_id="ws-a", tier="business", meta_learning_opt_out=True
            )
        )
        store.save(
            WorkspaceSettings(
                workspace_id="ws-b", tier="free", meta_learning_opt_out=False
            )
        )

        a = store.get("ws-a")
        b = store.get("ws-b")
        assert a.tier == "business"
        assert a.meta_learning_opt_out is True
        assert b.tier == "free"
        assert b.meta_learning_opt_out is False

    def test_cross_user_no_leak(self, tmp_path):
        """User A cannot see User B's data in a different workspace."""
        store = SQLiteProjectStore(str(tmp_path / "test.db"))
        store.initialize()
        store.save(
            Project(
                id=new_project_id(),
                user_id="user-b",
                name="Secret Project",
                workspace_id="ws-private",
            )
        )

        # User A queries the same workspace -- no results because different user_id
        results = store.list_by_tenant(user_id="user-a", workspace_id="ws-private")
        assert len(results) == 0

    def test_scenario_isolation_across_workspaces(self, tmp_path):
        """Scenarios are isolated by user_id + workspace_id."""
        from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
        from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

        store = SQLiteScenarioStore(str(tmp_path / "test.db"))
        store.initialize()

        store.save(
            Scenario(
                id=new_scenario_id(),
                name="Base Case WS1",
                base_model="solar_pv",
                user_id="user-a",
                workspace_id="ws-1",
            )
        )
        store.save(
            Scenario(
                id=new_scenario_id(),
                name="Base Case WS2",
                base_model="solar_pv",
                user_id="user-a",
                workspace_id="ws-2",
            )
        )
        store.save(
            Scenario(
                id=new_scenario_id(),
                name="Other User",
                base_model="solar_pv",
                user_id="user-b",
                workspace_id="ws-1",
            )
        )

        ws1_user_a = store.list(user_id="user-a", workspace_id="ws-1")
        ws2_user_a = store.list(user_id="user-a", workspace_id="ws-2")
        ws1_user_b = store.list(user_id="user-b", workspace_id="ws-1")

        assert len(ws1_user_a) == 1
        assert ws1_user_a[0].name == "Base Case WS1"
        assert len(ws2_user_a) == 1
        assert ws2_user_a[0].name == "Base Case WS2"
        assert len(ws1_user_b) == 1
        assert ws1_user_b[0].name == "Other User"

    def test_workspace_default_settings_isolated(self):
        """Querying a workspace that has no saved settings returns safe defaults."""
        conn = sqlite3.connect(":memory:")
        store = WorkspaceSettingsStore(conn)

        # Save settings for ws-a only
        store.save(
            WorkspaceSettings(
                workspace_id="ws-a",
                tier="enterprise",
                meta_learning_opt_out=True,
            )
        )

        # ws-b has no saved settings -- should return defaults
        b = store.get("ws-b")
        assert b.workspace_id == "ws-b"
        assert b.tier == "free"
        assert b.meta_learning_opt_out is False
        assert b.meta_learning_enabled is True

        # ws-a retains its settings
        a = store.get("ws-a")
        assert a.tier == "enterprise"
        assert a.meta_learning_opt_out is True
        assert a.meta_learning_enabled is True  # Enterprise overrides opt-out
