# Plan 6 — Gestnova Integration + VDR Sharing + 4-tier Privacy

**Status:** In Progress (2026-05-25)
**Estimated:** 12-14h (2 sessions)
**Owner:** Aurora (laptop + Codex)

---

## Goal

Integrar el agente financiero (`asset-finance-modeler`, 498 tests, 56 MCP tools)
en el agente de voz de Gestnova (`livekit-voice-platform`) como **sub-agent
delegado**. Cuando un user habla con Gestnova y pide un análisis financiero,
el voice agent delega al financial sub-agent (Claude Agent SDK) que tiene
acceso al MCP de finanzas. El sub-agent genera un artifact HTML/PDF que se
muestra automáticamente en el doc-viewer del WebOS, y se puede compartir vía
VDR del workspace para colaboración entre users.

## Architecture — 4-tier Privacy

```
Capa 1 — PRIVADO (default)
  Projects, Scenarios, WizardSessions  scope: user_id
  Default: solo el dueño los ve

Capa 2 — VDR WORKSPACE (compartido controlado)
  User publica → bundle (HTML + JSON config + metadata)
  VDR workspace gestiona (reusa Gestnova existing infra)
  Otros del workspace: read-only

Capa 3 — CLONE PRIVADO (espacio del que clona)
  "Iterar con agente" → new Scenario en espacio del cloner
  Lineage: imported_from_vdr_<file_id>

Capa 4 — META-LEARNING GLOBAL (anónimo, opt-out por defecto)
  MetaLearner.extract_insights → KB global sin user_id ni workspace_id
  Disclaimer visible en Settings
  Opt-in obligatorio para workspaces marcados B2B-Enterprise
```

## Tasks

### T1 — Refactor schemas: tenant_id → user_id + workspace_id [1h]
- [ ] `store/projects.py`: rename column `tenant_id` → `user_id`, add `workspace_id`
- [ ] `store/scenarios.py`: rename + add (currently has `tenant_id` default)
- [ ] `wizard/persistence.py`: rename + add
- [ ] Migration script for existing DBs
- [ ] All queries updated to scope by `(user_id, workspace_id)`
- [ ] Update tests `test_tenant_isolation.py`

### T2 — 4 VDR-aware MCP tools in asset-finance-modeler [2h]
- [ ] `financial.share_to_vdr(scenario_id, visibility)` → packages HTML+JSON+metadata, POSTs to Gestnova VDR API, returns `vdr_file_id`
- [ ] `financial.import_from_vdr(vdr_file_id)` → fetches from VDR, creates cloned Scenario in current user's space with `parent_scenario_id=imported_from:<vdr_file_id>`
- [ ] `financial.list_workspace_shared(workspace_id)` → lists scenarios shared in this workspace (via VDR API)
- [ ] `financial.explain_vdr(vdr_file_id)` → reads JSON config, narrates inputs+assumptions+results without running model again

### T3 — Bridge VDR API ↔ asset-finance [1.5h]
- [ ] HTTP client in `intelligence/vdr_client.py` calling Gestnova `/api/vdr/upload` and `/api/vdr/get`
- [ ] Auth: bearer token passed via env `GESTNOVA_VDR_TOKEN`
- [ ] Tests with mocked Gestnova endpoint

### T4 — Meta-learning privacy split [1h]
- [ ] `MetaLearner.persist(insight, anonymize: bool=True)` — if anonymize, strips user_id/workspace_id, hashes scenario_id
- [ ] Settings DB table: `workspace_settings` with `meta_learning_opt_out: bool`
- [ ] Default: False (opt-out, contribute by default) for non-Enterprise workspaces
- [ ] Default: True (opt-in only) for `tier='enterprise'` workspaces

### T5 — MCP client Node in livekit-voice-platform [1h]
- [ ] `npm install @modelcontextprotocol/sdk` (same pattern as sentinelsec)
- [ ] `src/skills/integrations/finance-mcp-client.ts` — spawns `asset-finance-modeler` MCP via stdio, lifecycle manager
- [ ] Idle timeout 5min, lazy connect

### T6 — Sub-agent skill in Gestnova [3h]
- [ ] New skill `src/skills/core/financial-analysis.skill.ts`
- [ ] 1 main tool: `financial.analyze(query, context)` that spawns Claude sub-agent
- [ ] Sub-agent uses Anthropic SDK with finance MCP client as tools
- [ ] System prompt for sub-agent: "Eres analista financiero senior con acceso a 56 tools del motor asset-finance-modeler. Wizard cuando hay que recoger inputs. Diff para iterar. Recall para recordar proyectos previos. NUNCA inventes números, solo de tools."
- [ ] Returns to voice agent: `{narrative: string, artifact_url: string, scenario_id: string}`

### T7 — Auto-open artifact in WebOS doc-viewer [1.5h]
- [ ] When financial sub-agent generates artifact, voice agent calls existing `aurora:doc:*` bridge to open doc-viewer with artifact URL
- [ ] Doc-viewer recognizes `kind=financial-report` → uses light theme + print CSS
- [ ] If artifact is in VDR, vdr-finder shows it with `[FINANCIAL]` badge + "Iterar con agente" button
- [ ] Button click → calls `financial.import_from_vdr` via skill tool

### T8 — Voice agent system prompt update [30min]
- [ ] System prompt: "Para análisis financiero, valoración, IRR, DSCR, CAPEX/OPEX, proyectos solares/eólicos/BESS/M&A → ALWAYS usa financial.analyze(...). NO inventes números financieros."
- [ ] User experience: voice agent says "déjame consultar con el analista financiero…" then awaits sub-agent result

### T9 — E2E tests [1h]
- [ ] User A voice → "evalúame planta solar 50MW Sevilla" → wizard → report → auto-open doc-viewer
- [ ] User A: "compártelo en el VDR" → VDR file created
- [ ] User B (same workspace): opens vdr-finder → sees [FINANCIAL] badge → clicks "Iterar" → new scenario in B's space
- [ ] User B: "cambia CAPEX a 600" → diff vs original
- [ ] MetaLearning insight extracted, persisted anonymously to global KB

### T10 — Multi-tenant isolation E2E test [30min]
- [ ] User A creates scenario → User B (different user, same workspace) cannot see in their `project.list()` (unless shared via VDR)
- [ ] User A and User B in different workspaces → complete isolation
- [ ] VDR-shared scenarios visible only within workspace

## Decisions made

1. **Privacy default**: user_id privado + workspace_id sharing vía VDR
2. **Meta-learning**: opt-out por defecto (transparente), opt-in para Enterprise tier
3. **Sub-agent pattern**: Claude Agent SDK + MCP client (no embedding 56 tools in voice agent)
4. **Artifact display**: auto-open en doc-viewer del WebOS al generarse
5. **VDR is single source of truth** for sharing — no parallel sharing mechanism

## Out of scope (Plan 7+)

- WhatsApp/email channels invoking financial agent
- Real-time collaboration (2 users editing same scenario)
- Audit log of who viewed which VDR scenario
- LBO/M&A specialized templates (genérico ya funciona)
- Live market data feeds (KB ingestion separate)

## State as of plan creation (2026-05-25 14:30)

- `asset-finance-modeler`: 498 tests, 56 MCP tools, multi-tenant scenarios fixed
- `livekit-voice-platform`: 30 skills, VDR infra exists, NO MCP client yet
- Both repos clean, all tests passing
