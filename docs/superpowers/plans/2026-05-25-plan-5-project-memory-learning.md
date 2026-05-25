# Project Memory + Learning Implementation Plan (Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add project-level organization, scenario diff/compare, semantic recall, wizard persistence, and meta-learning so the agent remembers every analysis, learns from each simulation, and can iterate on previous work.

**Architecture:** Multi-tenant from day 1 (tenant_id on all tables). Project model groups scenarios. Scenario diff computes input deltas + KPI changes. Semantic recall via FAISS embeddings on scenario metadata. Meta-learning extracts insights from completed runs into KB.

**Tech Stack:** Python 3.12+, SQLite, FAISS, Pydantic v2, pytest

**Depends on:** Plans 1-4 (complete, 433 tests)

---

## File Structure

```
src/asset_finance_modeler/
  store/
    projects.py          → NEW: Project model + SQLiteProjectStore
    scenarios.py         ← MODIFY: add tenant_id column
  core/
    scenario_diff.py     → NEW: diff two scenarios (input deltas + KPI changes)
  intelligence/
    recall.py            → NEW: semantic scenario recall via FAISS
    learning.py          → NEW: meta-learning — extract insights from runs
  wizard/
    persistence.py       → NEW: persist/resume WizardSession in SQLite
  mcp_server/tools/
    projects.py          → NEW: project.create/list/get/archive tools
    scenario_recall.py   → NEW: scenario.recall + scenario.diff tools
    registry.py          ← MODIFY: register new tools

tests/unit/
  test_projects.py
  test_scenario_diff.py
  test_recall.py
  test_learning.py
  test_wizard_persistence.py
  test_project_mcp_tools.py
```

---

### Task 1: Project Model + Store

**Files:**
- Create: `src/asset_finance_modeler/store/projects.py`
- Test: `tests/unit/test_projects.py`

A Project groups related scenarios under a tenant, with name, description, tags, and metadata.

### Task 2: Scenario Diff

**Files:**
- Create: `src/asset_finance_modeler/core/scenario_diff.py`
- Test: `tests/unit/test_scenario_diff.py`

Compare two scenarios: which inputs changed, how KPIs moved. Returns structured DiffResult.

### Task 3: Wizard Session Persistence

**Files:**
- Create: `src/asset_finance_modeler/wizard/persistence.py`
- Test: `tests/unit/test_wizard_persistence.py`

Save/load WizardSession to SQLite so users can resume interrupted wizards.

### Task 4: Semantic Scenario Recall

**Files:**
- Create: `src/asset_finance_modeler/intelligence/recall.py`
- Test: `tests/unit/test_recall.py`

FAISS index over scenario metadata (name, description, tags, asset_type, KPIs) for semantic search. "Remember the solar project from Tuesday" → finds matching scenarios.

### Task 5: Meta-Learning Layer

**Files:**
- Create: `src/asset_finance_modeler/intelligence/learning.py`
- Test: `tests/unit/test_learning.py`

After each scenario run, extract insights: actual DSCR vs target, IRR vs preset expectation, CAPEX/production ratios. Store as unverified KB entries for analyst batch review.

### Task 6: MCP Tools + Project Context Narrative

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/projects.py`
- Create: `src/asset_finance_modeler/mcp_server/tools/scenario_recall.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Test: `tests/unit/test_project_mcp_tools.py`

New tools: project.create, project.list, project.get, project.archive, scenario.diff, scenario.recall, agent.recall_project_context (narrative summary).
