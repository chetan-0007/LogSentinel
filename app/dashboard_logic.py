from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict


def get_recent_logs_logic(limit: int, db: Session) -> List[Dict]:
    query = text("""
        SELECT id, service, level, message, event_time, latency_ms, status_code
        FROM logs
        ORDER BY event_time DESC
        LIMIT :limit
    """)
    logs = db.execute(query, {"limit": limit}).fetchall()
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
        SELECT service, last_alert_time, is_active
        FROM service_alerts
        WHERE is_active = TRUE
        ORDER BY last_alert_time DESC
    """)
    alerts = db.execute(query).fetchall()
    return [
        {
            "service": alert.service,
            "triggered_at": alert.last_alert_time.isoformat() if alert.last_alert_time else None,
            "status": "ACTIVE",
        }
        for alert in alerts
    ]


def get_alert_history_logic(limit: int, db: Session) -> List[Dict]:
    query = text("""
        SELECT service, error_rate, baseline_rate, triggered_at
        FROM alert_history
        ORDER BY triggered_at DESC
        LIMIT :limit
    """)
    history = db.execute(query, {"limit": limit}).fetchall()
    return [
        {
            "service": h.service,
            "error_rate": float(h.error_rate) if h.error_rate else 0,
            "baseline_rate": float(h.baseline_rate) if h.baseline_rate else 0,
            "timestamp": h.triggered_at.isoformat() if h.triggered_at else None,
        }
        for h in history
    ]


def get_error_rates_logic(db: Session) -> List[Dict]:
    query = text("""
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
        GROUP BY service
        ORDER BY error_percentage DESC
    """)
    stats = db.execute(query).fetchall()
    return [
        {
            "service": s.service,
            "error_rate": float(s.error_percentage) if s.error_percentage else 0,
            "total_logs": s.total_logs,
        }
        for s in stats
    ]
