"""Agentic root-cause analysis.

Runs when a new alert is triggered. It performs a deterministic multi-step
investigation over the logs, then asks Claude to synthesize a structured RCA
report. The report is stored on the alert row (`alerts.rca_report`, JSONB).

Steps:
  1. Fetch logs from 10 minutes before and after the alert timestamp for the
     affected service.
  2. Identify the first error occurrence (timestamp + log line).
  3. Check all other services for correlated errors in the same window
     (cascade detection).
  4. Generate a structured RCA JSON report (LLM synthesis, with a deterministic
     fallback when ANTHROPIC_API_KEY is unset).
"""
import json
import re
from datetime import timedelta

from sqlalchemy import text

from app.database import SessionLocal
from app.config import LLM_MODEL, ANTHROPIC_API_KEY

WINDOW_MINUTES = 10


def _load_alert(db, alert_id: int):
    return db.execute(
        text("SELECT id, service, triggered_at, error_rate FROM alerts WHERE id = :id"),
        {"id": alert_id},
    ).fetchone()


def _logs_in_window(db, service: str, start, end, only_errors=False, limit=200):
    clause = "AND level = 'ERROR'" if only_errors else ""
    rows = db.execute(
        text(f"""
            SELECT service, level, status_code, endpoint, message, event_time
            FROM logs
            WHERE service = :service
              AND event_time BETWEEN :start AND :end
              {clause}
            ORDER BY event_time ASC
            LIMIT :limit
        """),
        {"service": service, "start": start, "end": end, "limit": limit},
    ).fetchall()
    return rows


def _correlated_error_services(db, service: str, start, end):
    """Other services with errors in the same window (cascade signal)."""
    rows = db.execute(
        text("""
            SELECT service, COUNT(*) AS error_count, MIN(event_time) AS first_error
            FROM logs
            WHERE level = 'ERROR'
              AND service != :service
              AND event_time BETWEEN :start AND :end
            GROUP BY service
            ORDER BY first_error ASC
        """),
        {"service": service, "start": start, "end": end},
    ).fetchall()
    return rows


def _fmt_log(r) -> str:
    lvl = r.level.value if hasattr(r.level, "value") else r.level
    ts = r.event_time.isoformat() if r.event_time else "?"
    return f"[{ts}] {lvl} {r.status_code or ''} {r.endpoint or ''} {r.message or ''}".strip()


def _synthesize_with_llm(context: str) -> dict | None:
    """Ask Claude for a structured RCA report. Returns None on failure/no key."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = (
            "You are a site reliability engineer performing root-cause analysis.\n"
            "Given the evidence below, respond with ONLY a JSON object with keys: "
            "root_cause (string), first_error_at (ISO timestamp or null), "
            "affected_services (array of strings), cascade_detected (boolean), "
            "confidence (\"HIGH\"|\"MEDIUM\"|\"LOW\"), recommended_action (string).\n\n"
            f"Evidence:\n{context}\n"
        )
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text_out = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        match = re.search(r"\{.*\}", text_out, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"[RCA] LLM synthesis failed: {e}")
    return None


def run_rca(alert_id: int) -> dict:
    """Run the RCA pipeline for an alert and persist the report. Returns the report."""
    db = SessionLocal()
    try:
        alert = _load_alert(db, alert_id)
        if not alert:
            return {"error": "alert_not_found", "alert_id": alert_id}

        service = alert.service
        center = alert.triggered_at
        start = center - timedelta(minutes=WINDOW_MINUTES)
        end = center + timedelta(minutes=WINDOW_MINUTES)

        # Step 1: window logs for the affected service
        window_logs = _logs_in_window(db, service, start, end)

        # Step 2: first error occurrence
        first_error = next(
            (r for r in window_logs
             if (r.level.value if hasattr(r.level, "value") else r.level) == "ERROR"),
            None,
        )
        first_error_at = first_error.event_time.isoformat() if first_error else None
        first_error_line = _fmt_log(first_error) if first_error else None

        # Step 3: cascade detection across other services
        correlated = _correlated_error_services(db, service, start, end)
        affected_services = [service] + [r.service for r in correlated]
        cascade_detected = len(correlated) > 0

        # Step 4: synthesize structured report
        error_lines = [
            _fmt_log(r) for r in window_logs
            if (r.level.value if hasattr(r.level, "value") else r.level) == "ERROR"
        ][:40]
        context = (
            f"Alert service: {service}\n"
            f"Alert time: {center.isoformat() if center else '?'}\n"
            f"Error rate at alert: {alert.error_rate}%\n"
            f"First error: {first_error_line or 'none found in window'}\n"
            f"Other services with errors in window: "
            f"{[{'service': r.service, 'errors': r.error_count} for r in correlated] or 'none'}\n\n"
            f"Error log lines ({len(error_lines)} shown):\n" + "\n".join(error_lines)
        )

        report = _synthesize_with_llm(context)
        if report is None:
            # Deterministic fallback report.
            report = {
                "root_cause": (
                    f"Elevated errors in {service}. First error: "
                    f"{first_error.message if first_error else 'unknown'}."
                ),
                "recommended_action": "Inspect the affected service logs and recent deploys.",
                "confidence": "LOW",
            }

        # Normalize / enforce the required schema fields.
        report.setdefault("root_cause", "Unknown")
        report["first_error_at"] = report.get("first_error_at") or first_error_at
        report["affected_services"] = report.get("affected_services") or affected_services
        report["cascade_detected"] = report.get("cascade_detected", cascade_detected)
        report.setdefault("confidence", "LOW")
        report.setdefault("recommended_action", "")

        db.execute(
            text("UPDATE alerts SET rca_report = CAST(:report AS JSONB) WHERE id = :id"),
            {"report": json.dumps(report), "id": alert_id},
        )
        db.commit()
        return report
    finally:
        db.close()


def get_rca(alert_id: int) -> dict | None:
    """Return the stored RCA report for an alert (or None)."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT rca_report FROM alerts WHERE id = :id"),
            {"id": alert_id},
        ).fetchone()
        if not row:
            return None
        return row.rca_report
    finally:
        db.close()
