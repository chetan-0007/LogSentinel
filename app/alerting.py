import os
import smtplib
from email.message import EmailMessage
from datetime import datetime


def send_email_alert(service: str, error_rate: float, baseline_rate: float, triggered_at: datetime, recovered: bool = False):
    """Send an email notification when an alert is triggered or recovered.

    Environment variables:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_TO, ALERT_FROM
    ALERT_TO may be a comma-separated list of recipients.
    """
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
    body = f"Service: {service}\nTime: {triggered_at.isoformat()}\nError rate: {error_rate}%\nBaseline: {baseline_rate if baseline_rate is not None else 'N/A'}%\n"
    if recovered:
        body = "RECOVERY\n" + body
    else:
        body = "ALERT\n" + body

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
