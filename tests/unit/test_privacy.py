from asset_finance_modeler.intelligence.privacy import (
    anonymize_insight,
    should_collect_meta_learning,
)


class TestAnonymizeInsight:
    def test_strips_pii(self):
        insight = {
            "user_id": "u123",
            "email": "test@test.com",
            "irr": 0.12,
            "npv": 1500000,
        }
        clean = anonymize_insight(insight)
        assert "user_id" not in clean
        assert "email" not in clean
        assert clean["irr"] == 0.12

    def test_hashes_ids(self):
        insight = {"scenario_id": "sc-123", "project_id": "proj-456", "value": 42}
        clean = anonymize_insight(insight)
        assert clean["scenario_id"] != "sc-123"
        assert len(clean["scenario_id"]) == 12
        assert clean["value"] == 42

    def test_preserves_non_pii(self):
        insight = {"technology": "solar", "capacity_mw": 50, "irr": 0.15}
        clean = anonymize_insight(insight)
        assert clean == insight


class TestMetaLearningCollection:
    def test_free_tier_default_collects(self):
        assert should_collect_meta_learning("free", opt_out=False) is True

    def test_free_tier_opt_out(self):
        assert should_collect_meta_learning("free", opt_out=True) is False

    def test_enterprise_always_collects(self):
        assert should_collect_meta_learning("enterprise", opt_out=True) is True

    def test_business_respects_opt_out(self):
        assert should_collect_meta_learning("business", opt_out=True) is False
        assert should_collect_meta_learning("business", opt_out=False) is True
