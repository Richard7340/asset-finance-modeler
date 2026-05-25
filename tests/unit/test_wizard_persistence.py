# tests/unit/test_wizard_persistence.py
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionOption, QuestionTemplate
from asset_finance_modeler.wizard.persistence import WizardSessionStore
from asset_finance_modeler.wizard.session import WizardSession


def _sample_questions():
    return [
        QuestionTemplate(field_path="production.capacity_mwp", question="Capacity?",
                         options=[QuestionOption(label="50", value=50)], required=True, order=1),
        QuestionTemplate(field_path="capex.amount", question="CAPEX?",
                         options=[], required=True, order=2),
    ]


def test_save_and_load(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    store.save(session, user_id="user-1")
    loaded = store.load(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.asset_type == "solar_pv"
    assert loaded.progress["answered"] == 1


def test_load_preserves_resolved_inputs(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="benchmark", provenance="Lazard", confidence=0.92,
                   benchmark_id="bm-capex-solar")
    store.save(session)
    loaded = store.load(session.session_id)
    ri = loaded.resolved["production.capacity_mwp"]
    assert ri.source == "benchmark"
    assert ri.confidence == 0.92


def test_load_nonexistent(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    assert store.load("nonexistent") is None


def test_delete_session(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    session = WizardSession.create("solar_pv", _sample_questions())
    store.save(session)
    store.delete(session.session_id)
    assert store.load(session.session_id) is None


def test_list_by_tenant(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    s1 = WizardSession.create("solar_pv", _sample_questions())
    s2 = WizardSession.create("bess", _sample_questions())
    store.save(s1, user_id="t1")
    store.save(s2, user_id="t1")
    sessions = store.list_by_tenant("t1")
    assert len(sessions) == 2


def test_resume_and_continue(tmp_path):
    store = WizardSessionStore(str(tmp_path / "wiz.db"))
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    store.save(session)
    loaded = store.load(session.session_id)
    result = loaded.answer(0.45, source="user", provenance="User", confidence=1.0)
    assert result.get("completed") is True
