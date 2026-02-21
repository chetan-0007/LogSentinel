from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from app.alerting import send_email_alert

multiplier = 2
static_threshold = 10
min_logs = 100


def get_baseline(db: Session) -> dict:

    query = text("""
        SELECT 
            service,
            ROUND(
                COUNT(*) FILTER (WHERE level = 'ERROR') * 100.0 
                / COUNT(*), 
                2
            ) AS baseline_error_percentage
        FROM logs
        WHERE event_time > CURRENT_TIMESTAMP - INTERVAL '1 hour'
        AND event_time <= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
        GROUP BY service
        HAVING COUNT(*) >= :min_logs
    """)

    results = db.execute(query, {"min_logs": min_logs}).fetchall()

    return {row.service: row.baseline_error_percentage for row in results}


def get_current_rate(db: Session) -> dict:

    query = text("""
        SELECT 
            service,
            ROUND(
                COUNT(*) FILTER (WHERE level = 'ERROR') * 100.0 
                / COUNT(*), 
                2
            ) AS error_percentage
        FROM logs
        WHERE event_time > CURRENT_TIMESTAMP - INTERVAL '10 minutes'
        GROUP BY service
        HAVING COUNT(*) >= :min_logs
    """)

    results = db.execute(query, {"min_logs": min_logs}).fetchall()

    return {row.service: row.error_percentage for row in results}


def _send_email_alert(service: str, error_rate: float, baseline_rate: float, triggered_at: datetime, recovered: bool = False):
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


COOLDOWN_MINUTES = 2


def check_error_rates(db: Session):

    baseline = get_baseline(db)
    current = get_current_rate(db)

    services_triggered = []
    now = datetime.now(timezone.utc)

    # Get all services we know about
    all_services = set(baseline.keys()) | set(current.keys())

    for service in all_services:

        current_rate = current.get(service, 0)
        baseline_rate = baseline.get(service)

        should_alert = False

        if current_rate > static_threshold:
            should_alert = True

        elif baseline_rate is not None and current_rate > baseline_rate * multiplier:
            should_alert = True

        alert_row = db.execute(
            text("""
                SELECT last_alert_time, is_active
                FROM service_alerts
                WHERE service = :service
            """),
            {"service": service},
        ).fetchone()

        # -----------------------------------
        # CASE 1 & 2 → SHOULD ALERT
        # -----------------------------------
        if should_alert:

            if alert_row:

                last_alert_time = alert_row.last_alert_time
                is_active = alert_row.is_active

                # Already active → check cooldown
                if is_active:
                    if now - last_alert_time < timedelta(minutes=COOLDOWN_MINUTES):
                        continue

                # Update alert state
                db.execute(
                    text("""
                        UPDATE service_alerts
                        SET last_alert_time = :now,
                            is_active = TRUE
                        WHERE service = :service
                    """),
                    {"now": now, "service": service},
                )

            else:
                # First time alert
                db.execute(
                    text("""
                        INSERT INTO service_alerts (service, last_alert_time, is_active)
                        VALUES (:service, :now, TRUE)
                    """),
                    {"service": service, "now": now},
                )

            # Insert alert history
            db.execute(
                text("""
                    INSERT INTO alert_history
                    (service, error_rate, baseline_rate, triggered_at)
                    VALUES (:service, :error_rate, :baseline_rate, :now)
                """),
                {
                    "service": service,
                    "error_rate": current_rate,
                    "baseline_rate": baseline_rate,
                    "now": now,
                },
            )

            services_triggered.append(service)
            # send notification email for alert
            try:
                send_email_alert(service, current_rate, baseline_rate, now, recovered=False)
            except Exception as e:
                print(f"[ALERT_MONITOR] email send failed: {e}")

        # -----------------------------------
        # CASE 3 → RECOVERY
        # -----------------------------------
        else:

            if alert_row and alert_row.is_active:

                # Mark as recovered
                db.execute(
                    text("""
                        UPDATE service_alerts
                        SET is_active = FALSE
                        WHERE service = :service
                    """),
                    {"service": service},
                )

                # Insert recovery history
                db.execute(
                    text("""
                        INSERT INTO alert_history
                        (service, error_rate, baseline_rate, triggered_at)
                        VALUES (:service, 0, :baseline_rate, :now)
                    """),
                    {
                        "service": service,
                        "baseline_rate": baseline_rate,
                        "now": now,
                    },
                )

                services_triggered.append(f"{service} RECOVERED")
                # send recovery email
                try:
                    send_email_alert(service, 0, baseline_rate, now, recovered=True)
                except Exception as e:
                    print(f"[ALERT_MONITOR] recovery email failed: {e}")

    db.commit()

    return services_triggered