import sqlite3

import pytest

from asset_finance_modeler.store.workspace_settings import (
    WorkspaceSettings,
    WorkspaceSettingsStore,
)


@pytest.fixture
def store():
    conn = sqlite3.connect(":memory:")
    return WorkspaceSettingsStore(conn)


class TestWorkspaceSettings:
    def test_default_settings(self, store):
        settings = store.get("ws-test")
        assert settings.workspace_id == "ws-test"
        assert settings.meta_learning_opt_out is False
        assert settings.tier == "free"
        assert settings.meta_learning_enabled is True

    def test_save_and_get(self, store):
        store.save(
            WorkspaceSettings(
                workspace_id="ws-1", meta_learning_opt_out=True, tier="business"
            )
        )
        settings = store.get("ws-1")
        assert settings.meta_learning_opt_out is True
        assert settings.tier == "business"
        assert settings.meta_learning_enabled is False

    def test_enterprise_always_enabled(self, store):
        store.save(
            WorkspaceSettings(
                workspace_id="ws-ent", meta_learning_opt_out=True, tier="enterprise"
            )
        )
        settings = store.get("ws-ent")
        assert settings.meta_learning_enabled is True  # Enterprise overrides opt-out

    def test_set_opt_out(self, store):
        store.set_opt_out("ws-2", True)
        assert store.get("ws-2").meta_learning_opt_out is True

    def test_set_tier(self, store):
        store.set_tier("ws-3", "personal")
        assert store.get("ws-3").tier == "personal"
