import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
import smtplib
from openai import OpenAI

# Load OpenAI API key from environment
# openai.api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def fetch_recent_logs(db: Session, service_name: str, limit: int = 50) -> str:
    """Fetch recent logs for a service from the database"""
    query = f"""
        SELECT status_code, level, message, endpoint, event_time
        FROM logs
        WHERE service = '{service_name}'
        ORDER BY event_time DESC
        LIMIT {limit}
    """
    rows = db.execute(text(query)).fetchall() 
    logs_text = "\n".join([f"{row[0]} {row[1]} {row[2]}" for row in rows])
    return logs_text or "No logs found."


def summarize_logs(log_text: str) -> str:
    """Call OpenAI GPT to summarize logs using 1.x+ API"""
    prompt = f"""
    You are a system reliability AI assistant.
    Summarize the following logs and provide:
    1. Likely root cause
    2. Suggested next steps

    Logs:
    {log_text}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[AI_SUMMARY_FAILED] {e}"


def send_email_alert(
    service: str,
    error_rate: float,
    baseline_rate: float,
    triggered_at: datetime,
    recovered: bool = False,
    db: Session = None,
    ai_summary: bool = True
):
    """Send an email notification with optional AI log summarization"""

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

    subject = (f"[RECOVERY] {service} recovered" if recovered else f"[ALERT] {service} high error rate")
    body = f"Service: {service}\nTime: {triggered_at.isoformat() if triggered_at else 'N/A'}\nError rate: {error_rate}%\nBaseline: {baseline_rate if baseline_rate is not None else 'N/A'}%\n"
    if recovered:
        body = "RECOVERY\n" + body
    else:
        body = "ALERT\n" + body

    # -----------------------------
    # AI log summary integration
    # -----------------------------
    if ai_summary and db:
        try:
            logs_text = fetch_recent_logs(db, service)
            summary = summarize_logs(logs_text)
            body += f"\n\nAI Root Cause Summary:\n{summary}"
        except Exception as e:
            body += f"\n\n[AI_SUMMARY_FAILED] {e}"

    # -----------------------------
    # Send email
    # -----------------------------
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
        print(f"[ALERT_EMAIL] Email sent for {service} (recovered={recovered}) to {recipients}")
    except Exception as e:
        print(f"[ALERT_EMAIL] Failed to send email: {e}")