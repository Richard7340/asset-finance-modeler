# Integration with Gestnova / Ian

## Bridge plan (3-4h)

After the modeler MCP server is live, wire it into `livekit-voice-platform` (Ian) as follows:

### 1. MCP connector configuration

Add an entry to the per-company MCP config (e.g. `config/companies/gestnova.json`):

```json
{
  "mcpServers": {
    "asset-finance-modeler": {
      "command": "python",
      "args": ["-m", "asset_finance_modeler.mcp_server.server"],
      "env": {
        "PYTHONPATH": "/path/to/asset-finance-modeler/src",
        "ASSET_FINANCE_DB_PATH": "/var/lib/gestnova/finance.db"
      }
    }
  }
}
```

### 2. Skill registry — `financial-analysis` skill

Create `src/skills/core/financial-analysis.skill.ts` declaring the MCP tools with LLM-friendly descriptions. The 17 `finance.simulate.*` tools become Ian's surface.

### 3. Prompt update for Ian

Ian needs to learn:
- When to declare assumptions (user has no data) vs use real data (V2)
- Conversational pattern: discover → load baseline → create scenario → run → compare → export
- Output format choice based on channel: summary in WhatsApp, report by email, dashboard via artifact

### 4. `buildModelInputsFromCompanyData` helper (V2 / when ready)

Extract `Expense`, `Invoice`, `Customer`, `Agent` from Prisma → produce a partial `SaasModelConfig` overlay. Use as overrides when running scenarios for Gestnova's own books.

### 5. Smoke test

E2E: WhatsApp message "Ian, simula Gestnova con bajada a 250€/agente, mándame el cash flow en Excel" should:
1. Trigger `finance.simulate.load_baseline` → `create_scenario` (override) → `run` → `export` (xlsx) → return file URL/path to user.

## Architecture invariants

- The modeler **never** renders UI / HTML / PDF. It returns structured data.
- Ian decides rendering (artifact dashboard, PDF via DocumentTemplate, CSV attachment, WhatsApp markdown).
- The modeler is multi-consumer: Aurora can use the same MCP, scripts can use the CLI.

## Cost / billing

Tokens used by Ian when reasoning over the modeler responses are billed normally. The modeler itself does no LLM calls (web search delegated to caller).
