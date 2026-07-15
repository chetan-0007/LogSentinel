"""Hybrid error-rate monitoring.

A cheap deterministic threshold pre-filter selects candidate services, then the
LangGraph observability agent (app.agents.monitoring_agent) reasons over each
candidate and decides whether to alert. If the agent is unavailable (no
ANTHROPIC_API_KEY) we fall back to a deterministic decision so monitoring keeps
working. Recovery is handled by resolving active alerts once a service is healthy
again.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone

from app.agents.monitoring_agent import (
    investigate_service,
    create_alert,
    resolve_alert_record,
)

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


def _fallback_severity(current_rate: float, baseline_rate) -> str:
    """Deterministic severity used when the LLM agent is unavailable."""
    if current_rate >= 50:
        return "CRITICAL"
    if current_rate >= 30:
        return "HIGH"
    if current_rate >= 15:
        return "MEDIUM"
    if baseline_rate is not None and current_rate > baseline_rate * multiplier:
        return "MEDIUM"
    return "LOW"


def _active_alert_services(db: Session) -> set:
    rows = db.execute(
        text("SELECT DISTINCT service FROM alerts WHERE status = 'ACTIVE'")
    ).fetchall()
    return {r.service for r in rows}


def _resolve_service(db: Session, service: str):
    """Resolve every active alert for a recovered service."""
    rows = db.execute(
        text("SELECT id FROM alerts WHERE service = :s AND status = 'ACTIVE'"),
        {"s": service},
    ).fetchall()
    for r in rows:
        resolve_alert_record(r.id)


def check_error_rates(db: Session):
    """Run one monitoring cycle. Returns a list of triggered/recovered services."""
    baseline = get_baseline(db)
    current = get_current_rate(db)

    services_triggered = []
    all_services = set(baseline.keys()) | set(current.keys())

    # ---- Pre-filter: pick candidate services worth investigating ----
    candidates = []
    for service in all_services:
        current_rate = current.get(service, 0)
        baseline_rate = baseline.get(service)

        should_investigate = (
            current_rate > static_threshold
            or (baseline_rate is not None and current_rate > baseline_rate * multiplier)
        )
        if should_investigate:
            candidates.append((service, current_rate, baseline_rate))

    # ---- Agent (or deterministic fallback) decides per candidate ----
    for service, current_rate, baseline_rate in candidates:
        try:
            decision = investigate_service(service, current_rate, baseline_rate)
            if decision.get("decision") == "alert" or decision.get("alert_id"):
                services_triggered.append(service)
        except Exception as e:
            # Agent unavailable or errored -> deterministic fallback.
            print(f"[ALERT_MONITOR] agent fallback for {service}: {e}")
            severity = _fallback_severity(current_rate, baseline_rate)
            reason = (
                f"Threshold breach: error rate {current_rate}% "
                f"(baseline {baseline_rate if baseline_rate is not None else 'N/A'}%)"
            )
            result = create_alert(
                service, severity, reason,
                error_rate=current_rate, baseline_rate=baseline_rate,
            )
            if result.get("status") == "created":
                services_triggered.append(service)

    # ---- Recovery: resolve active alerts for services no longer breaching ----
    candidate_services = {c[0] for c in candidates}
    for service in _active_alert_services(db):
        if service in candidate_services:
            continue
        current_rate = current.get(service, 0)
        baseline_rate = baseline.get(service)
        still_breaching = (
            current_rate > static_threshold
            or (baseline_rate is not None and current_rate > baseline_rate * multiplier)
        )
        if not still_breaching:
            _resolve_service(db, service)
            services_triggered.append(f"{service} RECOVERED")

    return services_triggered
