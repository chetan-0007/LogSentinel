from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict


def get_recent_logs_logic(limit: int, db: Session, service: str = None) -> List[Dict]:
    base_query = """
        SELECT id, service, level, message, event_time, latency_ms, status_code
        FROM logs
    """
    params = {"limit": limit}
    if service:
        base_query += " WHERE service = :service"
        params["service"] = service
    base_query += " ORDER BY event_time DESC LIMIT :limit"

    logs = db.execute(text(base_query), params).fetchall()
    return [
        {
            "id": log.id,
            "service": log.service,
            "level": log.level,
            "message": log.message,
            "timestamp": log.event_time.isoformat() if log.event_time else None,
            "latency_ms": log.latency_ms,
            "status_code": log.status_code,
        }
        for log in logs
    ]


def get_active_alerts_logic(db: Session) -> List[Dict]:
    query = text("""
        SELECT id, service, severity, error_rate, agent_reasoning, triggered_at
        FROM alerts
        WHERE status = 'ACTIVE'
        ORDER BY triggered_at DESC
    """)
    alerts = db.execute(query).fetchall()
    return [
        {
            "id": alert.id,
            "service": alert.service,
            "severity": alert.severity,
            "error_rate": float(alert.error_rate) if alert.error_rate is not None else None,
            "agent_reasoning": alert.agent_reasoning,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
            "status": "ACTIVE",
        }
        for alert in alerts
    ]


def get_alert_history_logic(limit: int, db: Session) -> List[Dict]:
    query = text("""
        SELECT id, service, severity, status, error_rate, baseline_rate,
               agent_reasoning, triggered_at
        FROM alerts
        ORDER BY triggered_at DESC
        LIMIT :limit
    """)
    history = db.execute(query, {"limit": limit}).fetchall()
    return [
        {
            "id": h.id,
            "service": h.service,
            "severity": h.severity,
            "status": h.status,
            "error_rate": float(h.error_rate) if h.error_rate else 0,
            "baseline_rate": float(h.baseline_rate) if h.baseline_rate else 0,
            "agent_reasoning": h.agent_reasoning,
            "timestamp": h.triggered_at.isoformat() if h.triggered_at else None,
        }
        for h in history
    ]


def get_error_rates_logic(db: Session, service: str = None) -> List[Dict]:
    base_query = """
        SELECT 
            service,
            ROUND(
                COUNT(*) FILTER (WHERE level = 'ERROR') * 100.0 
                / NULLIF(COUNT(*), 0), 
                2
            ) AS error_percentage,
            COUNT(*) as total_logs
        FROM logs
        WHERE event_time > CURRENT_TIMESTAMP - INTERVAL '1 hour'
    """
    params = {}
    if service:
        base_query += " AND service = :service"
        params["service"] = service
    base_query += " GROUP BY service ORDER BY error_percentage DESC"

    stats = db.execute(text(base_query), params).fetchall()
    return [
        {
            "service": s.service,
            "error_rate": float(s.error_percentage) if s.error_percentage else 0,
            "total_logs": s.total_logs,
        }
        for s in stats
    ]
