# MCP Integration + Dashboard Implementation Plan (Plan 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make infrastructure models fully operational via MCP — load presets, run scenarios, get results, generate HTML dashboards with interactive charts.

**Architecture:** Extend existing MCP registry with infrastructure support. Add dashboard generator using Chart.js (self-contained HTML). Update execute.py to use protocol-based dispatch.

**Tech Stack:** Python 3.12+, Jinja2 (already dep), Chart.js (CDN), MCP tools

**Depends on:** Plan 1 + Plan 2 (completed)

---

### Task 1: MCP execute.py — Use protocol dispatch for run

Update execute.py to use `run_scenario` (the new dispatcher) instead of `run_scenario_saas`.

### Task 2: MCP registry — Register infrastructure tools

Update registry.py to include infrastructure presets in discovery and baseline loading.

### Task 3: Dashboard artifact generator

Create `mcp_server/tools/dashboard.py` with a tool that generates a self-contained HTML file with Chart.js visualizations of scenario results.

Charts included:
- Executive summary KPIs cards
- Revenue timeline (stacked by stream)
- P&L waterfall (revenue → COGS → OPEX → EBITDA → Net Income)
- Cash flow timeline (CFO, CFI, CFF, cumulative cash)
- DSCR timeline with covenant threshold
- Sensitivity heatmap (if available)
- Balance sheet evolution
- Input summary table

### Task 4: Integration tests — E2E MCP flow

Test the full MCP flow: list_models → load_baseline → run → get_results → generate dashboard.
