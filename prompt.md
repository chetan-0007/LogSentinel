You are a senior software engineer helping me upgrade an existing project called LogSentinel 
— an AI-powered distributed log monitoring platform.

The existing codebase uses:
- FastAPI (API layer)
- Apache Kafka (log streaming)
- PostgreSQL (storage)
- Docker Compose (orchestration)
- OpenAI API (currently just for text summarization)

First, thoroughly analyze the entire codebase — understand all existing:
- API endpoints and their request/response shapes
- Database models and schema
- Kafka producer/consumer setup
- Docker Compose service definitions
- Environment variables and config

Then implement the following 3 upgrades in order. Do not break any existing functionality.

---

## UPGRADE 1 — MCP Server

Build a new file `mcp_server.py` at the root level using the `mcp` Python SDK (`pip install mcp`).

Expose the following tools by calling the existing FastAPI endpoints internally:
- `get_active_alerts()` — calls GET /api/alerts/active
- `get_alert_history()` — calls GET /api/alerts/history
- `get_recent_logs(service: str, limit: int = 50)` — calls GET /api/logs/recent
- `get_error_rates(service: str)` — calls GET /api/stats/error-rates
- `trigger_alert_check()` — calls GET /alerts/check

The MCP server should run as a standalone process (stdio transport) so it works with 
Claude Desktop and Cursor's MCP client out of the box.

Add `mcp_server.py` as a new service in docker-compose.yml.
Add MCP server setup instructions to README.

---

## UPGRADE 2 — Replace Rule-Based Monitoring with an LLM Agent

Locate the existing monitoring engine (the background thread / scheduler that checks 
error rates and triggers alerts).

Replace the simple threshold logic with a LangGraph agent. Install: `pip install langgraph langchain-anthropic`

The agent should have access to these tools (implemented as Python functions that query 
the existing PostgreSQL database directly using SQLAlchemy):
- `get_error_rate(service: str, window_minutes: int)` 
- `get_recent_logs(service: str, limit: int)`
- `get_alert_history(service: str, days: int)`
- `trigger_alert(service: str, severity: str, reason: str)`  — writes to DB + sends email
- `resolve_alert(alert_id: int)`

Agent behavior:
- Runs on the same schedule as the existing monitoring engine
- Receives a system prompt explaining it is an observability agent
- Reasons across error rate, log content, and alert history before deciding to alert
- Assigns severity: LOW / MEDIUM / HIGH / CRITICAL based on reasoning
- Never double-alerts the same service within 30 minutes
- Returns structured JSON: { decision, severity, reasoning, recommended_action }

Store the agent's reasoning trace in a new postgres column `agent_reasoning` on the alerts table.

---

## UPGRADE 3 — Agentic Root Cause Analysis

Find where the existing AI summary is generated (OpenAI call for summarization).

Replace it with a multi-step RCA agent that runs when a new alert is triggered:

Step 1 — Fetch logs from the 10 minutes before and after the alert timestamp for the affected service
Step 2 — Identify the first error occurrence (timestamp + log line)
Step 3 — Check all other services for correlated errors in the same time window (cascade detection)
Step 4 — Generate structured RCA output:
{
  "root_cause": "...",
  "first_error_at": "ISO timestamp",
  "affected_services": ["svc1", "svc2"],
  "cascade_detected": true/false,
  "confidence": "HIGH/MEDIUM/LOW",
  "recommended_action": "..."
}

Store this JSON in a new postgres column `rca_report` on the alerts table.
Expose it via a new endpoint: GET /api/alerts/{alert_id}/rca
Display it in the existing dashboard UI.

---

## UPGRADE 4 — Deployment Setup

Set up the project for free deployment using Railway.app:

1. Create a `railway.toml` config file at root with services for: api, consumer, monitoring-agent, mcp-server
2. Update docker-compose.yml to use environment variable references compatible with Railway
3. Create a `Procfile` as fallback
4. Update README with:
   - One-click Railway deploy button
   - All required environment variables listed
   - How to connect MCP server to Claude Desktop (with exact config JSON)
   - How to connect to Cursor MCP client

Use Anthropic Claude API (model: claude-sonnet-4-6) instead of OpenAI for all LLM calls 
going forward. Use the `anthropic` Python SDK.

Required new environment variables to add to .env.example:
- ANTHROPIC_API_KEY
- RAILWAY_ENVIRONMENT (optional, for detecting prod vs local)

---

## FINAL CHECKLIST before you finish:

- [ ] All existing endpoints still work
- [ ] `docker compose up --build` starts everything including MCP server
- [ ] MCP server tools are testable via `mcp dev mcp_server.py`
- [ ] Agent reasoning is visible in the dashboard
- [ ] RCA report shows on alert detail view
- [ ] README has deployment instructions and MCP connection config
- [ ] requirements.txt updated with all new dependencies
- [ ] .env.example updated with all new variables

After analyzing the codebase, tell me:
1. What files you found and their purpose
2. Any conflicts or issues you see before starting
3. Then proceed upgrade by upgrade, confirming before moving to the next.
