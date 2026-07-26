"""LangGraph-based observability monitoring agent.

The agent investigates a candidate service (already flagged by a cheap
threshold pre-filter in `app.monitoring`) and decides whether to raise an
alert, reasoning across the current error rate, recent log content, and prior
alert history. It assigns a severity, avoids double-alerting within 30 minutes,
and returns a structured JSON decision.

If the configured provider has no API key, the agent is unavailable and callers
fall back to a deterministic decision (see `app.monitoring`).
"""
import json
import re
import contextvars
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.database import SessionLocal
from app.config import (
    LLM_MODEL,
    ANTHROPIC_API_KEY,
    GROQ_API_KEY,
    LLM_PROVIDER,
    LLM_MAX_RETRIES,
    LLM_RETRY_DELAY_SECONDS,
)

DEDUP_MINUTES = 30
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

# Captures alert ids created during a single agent invocation so the caller can
# enrich them with the agent's full reasoning trace afterwards.
_created_alerts: contextvars.ContextVar = contextvars.ContextVar("created_alerts", default=None)


SYSTEM_PROMPT = """You are LogSentinel's autonomous observability agent.

You are given ONE candidate service that a threshold pre-filter has flagged as
potentially unhealthy. Your job is to investigate and decide whether a human
should be alerted.

Available tools:
- get_error_rate(service, window_minutes): current error rate and log volume
- get_recent_logs(service, limit): recent log lines to inspect content
- get_alert_history(service, days): prior alerts for this service
- trigger_alert(service, severity, reason): raise an alert (writes DB + email)
- resolve_alert(alert_id): mark an alert resolved

Guidance:
1. Investigate before deciding. Look at the error rate, read recent logs to
   understand WHAT is failing, and check history for recurring/flapping issues.
2. Only alert on a genuine, actionable problem. Ignore transient blips.
3. Assign severity by impact:
   - LOW: minor/isolated errors, no user impact
   - MEDIUM: elevated errors, partial degradation
   - HIGH: significant failures affecting many requests
   - CRITICAL: service effectively down or cascading failure
4. Never raise a duplicate alert for a service already alerted in the last 30
   minutes (the trigger_alert tool enforces this too).
5. If you decide to alert, call trigger_alert exactly once.

When you are done, respond with ONLY a JSON object (no prose, no code fences):
{"decision": "alert" | "no_alert", "severity": "LOW|MEDIUM|HIGH|CRITICAL",
 "reasoning": "...", "recommended_action": "..."}
"""


# --------------------------------------------------------------------------
# Authoritative alert creation (shared by the tool and the deterministic
# fallback in app.monitoring).
# --------------------------------------------------------------------------
def create_alert(service: str, severity: str, reason: str,
                 error_rate: float = None, baseline_rate: float = None,
                 run_rca: bool = True, send_email: bool = True) -> dict:
    """Create an alert with 30-minute dedup. Returns {alert_id|None, status}."""
    severity = (severity or "MEDIUM").upper()
    if severity not in VALID_SEVERITIES:
        severity = "MEDIUM"

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        recent = db.execute(
            text("""
                SELECT id FROM alerts
                WHERE service = :service
                  AND (status = 'ACTIVE'
                       OR triggered_at > CURRENT_TIMESTAMP - make_interval(mins => :mins))
                ORDER BY triggered_at DESC
                LIMIT 1
            """),
            {"service": service, "mins": DEDUP_MINUTES},
        ).fetchone()

        if recent:
            return {"alert_id": recent.id, "status": "skipped_duplicate"}

        row = db.execute(
            text("""
                INSERT INTO alerts
                    (service, severity, status, error_rate, baseline_rate, reason, triggered_at)
                VALUES (:service, :severity, 'ACTIVE', :error_rate, :baseline_rate, :reason, :now)
                RETURNING id
            """),
            {
                "service": service,
                "severity": severity,
                "error_rate": error_rate,
                "baseline_rate": baseline_rate,
                "reason": reason,
                "now": now,
            },
        ).fetchone()
        alert_id = row.id

        # Bookkeeping table used for active-state tracking / recovery.
        existing = db.execute(
            text("SELECT service FROM service_alerts WHERE service = :s"),
            {"s": service},
        ).fetchone()
        if existing:
            db.execute(
                text("""UPDATE service_alerts
                        SET last_alert_time = :now, is_active = TRUE
                        WHERE service = :s"""),
                {"now": now, "s": service},
            )
        else:
            db.execute(
                text("""INSERT INTO service_alerts (service, last_alert_time, is_active)
                        VALUES (:s, :now, TRUE)"""),
                {"s": service, "now": now},
            )

        db.commit()
    finally:
        db.close()

    # Track created alert for the current agent invocation (if any).
    bucket = _created_alerts.get()
    if bucket is not None:
        bucket.append(alert_id)

    # Root-cause analysis (best-effort). Imported lazily to avoid import cycles.
    if run_rca:
        try:
            from app.agents.rca_agent import run_rca
            run_rca(alert_id)
        except Exception as e:
            print(f"[MONITOR_AGENT] RCA failed for alert {alert_id}: {e}")

    if send_email:
        try:
            from app.alerting import send_alert_email
            send_alert_email(alert_id)
        except Exception as e:
            print(f"[MONITOR_AGENT] email failed for alert {alert_id}: {e}")

    return {"alert_id": alert_id, "status": "created"}


def resolve_alert_record(alert_id: int) -> dict:
    """Mark an alert resolved and clear its service active-state flag."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = db.execute(
            text("""UPDATE alerts SET status = 'RESOLVED', resolved_at = :now
                    WHERE id = :id AND status != 'RESOLVED'
                    RETURNING service"""),
            {"now": now, "id": alert_id},
        ).fetchone()
        if row:
            db.execute(
                text("UPDATE service_alerts SET is_active = FALSE WHERE service = :s"),
                {"s": row.service},
            )
        db.commit()
        return {"alert_id": alert_id, "status": "resolved" if row else "not_found"}
    finally:
        db.close()


# --------------------------------------------------------------------------
# Agent construction
# --------------------------------------------------------------------------
def _build_agent():
    """Build the LangGraph react agent, or return None if the configured provider is unavailable."""
    provider = (LLM_PROVIDER or "anthropic").strip().lower()

    if provider == "groq":
        if not GROQ_API_KEY:
            return None
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise RuntimeError("langchain-groq is not installed") from exc
        model = ChatGroq(model=LLM_MODEL, api_key=GROQ_API_KEY, temperature=0)
    else:
        if not ANTHROPIC_API_KEY:
            return None
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("langchain-anthropic is not installed") from exc
        model = ChatAnthropic(model=LLM_MODEL, api_key=ANTHROPIC_API_KEY, temperature=0)

    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    @tool
    def get_error_rate(service: str, window_minutes: int = 10) -> dict:
        """Return the error-rate percentage and log volume for a service over the last window_minutes."""
        db = SessionLocal()
        try:
            row = db.execute(
                text("""
                    SELECT
                        ROUND(COUNT(*) FILTER (WHERE level = 'ERROR') * 100.0
                            / NULLIF(COUNT(*), 0), 2) AS error_rate,
                        COUNT(*) AS total_logs
                    FROM logs
                    WHERE service = :service
                      AND event_time > CURRENT_TIMESTAMP - make_interval(mins => :mins)
                """),
                {"service": service, "mins": window_minutes},
            ).fetchone()
            return {
                "service": service,
                "window_minutes": window_minutes,
                "error_rate": float(row.error_rate) if row and row.error_rate is not None else 0.0,
                "total_logs": int(row.total_logs) if row else 0,
            }
        finally:
            db.close()

    @tool
    def get_recent_logs(service: str, limit: int = 30) -> list:
        """Return recent log lines (level, status_code, endpoint, message, time) for a service."""
        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT level, status_code, endpoint, message, event_time
                    FROM logs
                    WHERE service = :service
                    ORDER BY event_time DESC
                    LIMIT :limit
                """),
                {"service": service, "limit": limit},
            ).fetchall()
            return [
                {
                    "level": r.level.value if hasattr(r.level, "value") else r.level,
                    "status_code": r.status_code,
                    "endpoint": r.endpoint,
                    "message": r.message,
                    "time": r.event_time.isoformat() if r.event_time else None,
                }
                for r in rows
            ]
        finally:
            db.close()

    @tool
    def get_alert_history(service: str, days: int = 7) -> list:
        """Return prior alerts for a service within the last N days."""
        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT id, severity, status, error_rate, reason, triggered_at
                    FROM alerts
                    WHERE service = :service
                      AND triggered_at > CURRENT_TIMESTAMP - make_interval(days => :days)
                    ORDER BY triggered_at DESC
                """),
                {"service": service, "days": days},
            ).fetchall()
            return [
                {
                    "id": r.id,
                    "severity": r.severity,
                    "status": r.status,
                    "error_rate": float(r.error_rate) if r.error_rate is not None else None,
                    "reason": r.reason,
                    "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
                }
                for r in rows
            ]
        finally:
            db.close()

    @tool
    def trigger_alert(service: str, severity: str, reason: str) -> dict:
        """Raise an alert for a service. Writes to the DB, runs RCA, and emails on-call.
        Enforces a 30-minute dedup window and returns the created alert id."""
        return create_alert(service, severity, reason)

    @tool
    def resolve_alert(alert_id: int) -> dict:
        """Mark an existing alert as resolved."""
        return resolve_alert_record(alert_id)

    tools = [get_error_rate, get_recent_logs, get_alert_history, trigger_alert, resolve_alert]
    return create_react_agent(model, tools, prompt=SYSTEM_PROMPT)


def _extract_text(message) -> str:
    """Pull plain text out of a LangChain message whose content may be a list of blocks."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _collect_service_context(service: str, current_rate: float, baseline_rate) -> str:
    """Build a compact prompt context for a direct LLM call (used by Groq)."""
    db = SessionLocal()
    try:
        recent_logs = db.execute(
            text("""
                SELECT level, status_code, endpoint, message, event_time
                FROM logs
                WHERE service = :service
                ORDER BY event_time DESC
                LIMIT 10
            """),
            {"service": service},
        ).fetchall()
        history = db.execute(
            text("""
                SELECT severity, status, reason, triggered_at
                FROM alerts
                WHERE service = :service
                  AND triggered_at > CURRENT_TIMESTAMP - make_interval(days => 1)
                ORDER BY triggered_at DESC
            """),
            {"service": service},
        ).fetchall()
    finally:
        db.close()

    log_lines = []
    for row in recent_logs:
        level = row.level.value if hasattr(row.level, "value") else row.level
        log_lines.append(
            f"[{row.event_time.isoformat() if row.event_time else '?'}] {level} {row.status_code or ''} {row.endpoint or ''} {row.message or ''}".strip()
        )

    history_lines = []
    for row in history:
        history_lines.append(
            f"[{row.triggered_at.isoformat() if row.triggered_at else '?'}] {row.severity}/{row.status}: {row.reason or ''}".strip()
        )

    return (
        f"Candidate service: {service}\n"
        f"Pre-filter current error rate (last 10 min): {current_rate}%\n"
        f"Baseline error rate (50-60 min ago): {baseline_rate if baseline_rate is not None else 'unknown'}%\n"
        f"Recent logs:\n" + ("\n".join(log_lines[:8]) if log_lines else "(none)") + "\n\n"
        f"Recent alert history:\n" + ("\n".join(history_lines[:8]) if history_lines else "(none)") + "\n\n"
        "Investigate and decide whether to alert. Return ONLY a JSON object with keys "
        "decision, severity, reasoning, recommended_action."
    )


def _invoke_groq_direct(service: str, current_rate: float, baseline_rate) -> dict:
    """Use a direct Groq chat completion instead of tool-calling, avoiding invalid tool message formats."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    prompt = _collect_service_context(service, current_rate, baseline_rate)
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("groq SDK is not installed") from exc

    client = Groq(api_key=GROQ_API_KEY)
    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                temperature=0,
                max_tokens=700,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are LogSentinel's autonomous observability agent. "
                            "Return ONLY JSON with decision, severity, reasoning, recommended_action."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text_out = response.choices[0].message.content or ""
            return _parse_decision(text_out)
        except Exception as exc:
            last_error = exc
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            raise RuntimeError(f"Groq request failed: {exc}") from exc

    if last_error is not None:
        raise RuntimeError(f"Groq request failed: {last_error}") from last_error
    return {"decision": "unknown", "severity": "MEDIUM", "reasoning": "", "recommended_action": ""}


def _parse_decision(text_out: str) -> dict:
    """Best-effort parse of the agent's final JSON decision."""
    match = re.search(r"\{.*\}", text_out, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "decision": "unknown",
        "severity": "MEDIUM",
        "reasoning": text_out.strip()[:2000],
        "recommended_action": "",
    }


def investigate_service(service: str, current_rate: float, baseline_rate) -> dict:
    """Run the agent against a single candidate service.

    Returns the structured decision dict. If the agent created an alert during
    the run, it is enriched with the full reasoning trace and recommended action.
    Raises RuntimeError if the configured LLM provider is unavailable.
    """
    provider = (LLM_PROVIDER or "anthropic").strip().lower()
    if provider == "groq":
        decision = _invoke_groq_direct(service, current_rate, baseline_rate)
        created = _created_alerts.get() or []
        if created:
            _enrich_alert(created[-1], decision)
            decision["alert_id"] = created[-1]
        return decision

    agent = _build_agent()
    if agent is None:
        raise RuntimeError(f"monitoring agent unavailable for provider '{LLM_PROVIDER}'")

    token = _created_alerts.set([])
    try:
        user_msg = (
            f"Candidate service: {service}\n"
            f"Pre-filter current error rate (last 10 min): {current_rate}%\n"
            f"Baseline error rate (50-60 min ago): "
            f"{baseline_rate if baseline_rate is not None else 'unknown'}%\n"
            f"Investigate and decide whether to alert."
        )
        result = agent.invoke({"messages": [{"role": "user", "content": user_msg}]})
        final = result["messages"][-1]
        decision = _parse_decision(_extract_text(final))

        created = _created_alerts.get() or []
        if created:
            _enrich_alert(created[-1], decision)
            decision["alert_id"] = created[-1]
        return decision
    finally:
        _created_alerts.reset(token)


def _enrich_alert(alert_id: int, decision: dict):
    """Store the agent's reasoning trace and recommended action on the alert row."""
    db = SessionLocal()
    try:
        db.execute(
            text("""
                UPDATE alerts
                SET agent_reasoning = :reasoning,
                    recommended_action = :action,
                    severity = COALESCE(:severity, severity)
                WHERE id = :id
            """),
            {
                "reasoning": json.dumps(decision, indent=2),
                "action": decision.get("recommended_action"),
                "severity": (decision.get("severity") or "").upper() if decision.get("severity") else None,
                "id": alert_id,
            },
        )
        db.commit()
    finally:
        db.close()
