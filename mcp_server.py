"""LogSentinel MCP server.

Exposes LogSentinel's observability data as MCP tools by proxying the existing
FastAPI endpoints over HTTP. Works with Claude Desktop and Cursor's MCP client.

Transport is selected via the MCP_TRANSPORT env var:
  - "stdio" (default): spawned on demand by an MCP client (Claude Desktop / Cursor)
  - "http":            long-running streamable-HTTP server (used by the container)

Run locally:      python mcp_server.py
Inspect/dev:      mcp dev mcp_server.py
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))
REQUEST_TIMEOUT = float(os.getenv("MCP_HTTP_TIMEOUT", "30"))

mcp = FastMCP("LogSentinel", host="0.0.0.0", port=MCP_PORT)


def _get(path: str, params: dict | None = None):
    """Call a LogSentinel API endpoint and return parsed JSON (or an error dict)."""
    url = f"{API_BASE_URL.rstrip('/')}{path}"
    try:
        resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
    except Exception as e:
        return {"error": "request_failed", "detail": str(e)}


@mcp.tool()
def get_active_alerts() -> list | dict:
    """List currently active alerts across all services."""
    return _get("/api/alerts/active")


@mcp.tool()
def get_alert_history(limit: int = 20) -> list | dict:
    """Return recent alert history (most recent first)."""
    return _get("/api/alerts/history", params={"limit": limit})


@mcp.tool()
def get_recent_logs(service: str, limit: int = 50) -> list | dict:
    """Return the most recent logs for a given service."""
    return _get("/api/logs/recent", params={"service": service, "limit": limit})


@mcp.tool()
def get_error_rates(service: str) -> list | dict:
    """Return the current (1h window) error rate for a given service."""
    return _get("/api/stats/error-rates", params={"service": service})


@mcp.tool()
def trigger_alert_check() -> dict | list:
    """Manually run the monitoring engine and return any services it triggered."""
    return _get("/alerts/check")


if __name__ == "__main__":
    if MCP_TRANSPORT == "http":
        # Long-running network transport for containerized/remote use.
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
