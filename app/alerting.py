"""Email alerting.

Sends an SMTP notification for an alert, embedding the agent's reasoning and the
structured RCA report (produced by app.agents.rca_agent). All LLM work now lives
in the agents; this module only formats and delivers email.

Environment variables:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_TO, ALERT_FROM
ALERT_TO may be a comma-separated list of recipients.
"""
import os
import json
import smtplib
from email.message import EmailMessage

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal


def fetch_recent_logs(db: Session, service_name: str, limit: int = 50) -> str:
    """Fetch recent logs for a service (parameterized to avoid SQL injection)."""
    query = text("""
        SELECT status_code, level, message, endpoint, event_time
        FROM logs
        WHERE service = :service
        ORDER BY event_time DESC
        LIMIT :limit
    """)
    rows = db.execute(query, {"service": service_name, "limit": limit}).fetchall()
    logs_text = "\n".join(f"{row[0]} {row[1]} {row[2]}" for row in rows)
    return logs_text or "No logs found."


def _smtp_send(subject: str, body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        print("[ALERT_EMAIL] SMTP_HOST not configured; skipping email")
        return

    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        smtp_port = 587

    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    alert_to = os.getenv("ALERT_TO")
    alert_from = os.getenv("ALERT_FROM", "alerts@example.com")

    if not alert_to:
        print("[ALERT_EMAIL] ALERT_TO not set; skipping email")
        return

    recipients = [a.strip() for a in alert_to.split(",") if a.strip()]

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = alert_from
    msg["To"] = ", ".join(recipients)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        print(f"[ALERT_EMAIL] Email sent to {recipients}")
    except Exception as e:
        print(f"[ALERT_EMAIL] Failed to send email: {e}")


def _format_rca(rca: dict) -> str:
    if not rca:
        return "RCA: (pending)"
    lines = ["AI Root Cause Analysis:"]
    lines.append(f"  Root cause: {rca.get('root_cause', 'unknown')}")
    lines.append(f"  First error at: {rca.get('first_error_at', 'n/a')}")
    lines.append(f"  Cascade detected: {rca.get('cascade_detected', False)}")
    affected = rca.get("affected_services") or []
    lines.append(f"  Affected services: {', '.join(affected) if affected else 'n/a'}")
    lines.append(f"  Confidence: {rca.get('confidence', 'n/a')}")
    lines.append(f"  Recommended action: {rca.get('recommended_action', 'n/a')}")
    return "\n".join(lines)


def send_alert_email(alert_id: int) -> None:
    """Load an alert and email its details, agent reasoning, and RCA report."""
    db = SessionLocal()
    try:
        alert = db.execute(
            text("""
                SELECT service, severity, error_rate, baseline_rate, reason,
                       recommended_action, agent_reasoning, rca_report, triggered_at
                FROM alerts WHERE id = :id
            """),
            {"id": alert_id},
        ).fetchone()
    finally:
        db.close()

    if not alert:
        print(f"[ALERT_EMAIL] alert {alert_id} not found; skipping email")
        return

    subject = f"[{alert.severity}] {alert.service} alert #{alert_id}"
    body_parts = [
        "ALERT",
        f"Service: {alert.service}",
        f"Severity: {alert.severity}",
        f"Time: {alert.triggered_at.isoformat() if alert.triggered_at else 'N/A'}",
        f"Error rate: {alert.error_rate}%",
        f"Baseline: {alert.baseline_rate if alert.baseline_rate is not None else 'N/A'}%",
        f"Reason: {alert.reason or 'n/a'}",
        f"Recommended action: {alert.recommended_action or 'n/a'}",
        "",
        _format_rca(alert.rca_report),
    ]
    if alert.agent_reasoning:
        body_parts += ["", "Agent reasoning:", alert.agent_reasoning]

    _smtp_send(subject, "\n".join(body_parts))
