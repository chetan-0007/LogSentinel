from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, engine, SessionLocal
from app.models import Log, Base
from app.schemas import LogCreate
from app.kafka_producer import send_log
from app import monitoring  # your monitoring module
from app.dashboard_logic import (
    get_recent_logs_logic,
    get_active_alerts_logic,
    get_alert_history_logic,
    get_error_rates_logic,
)
from app.logs import create_log_logic
import os
import threading
import time

app = FastAPI()

# Create DB tables on startup
@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

    # Start the background monitor in-process unless a dedicated monitoring-agent
    # service is running (set RUN_MONITOR_IN_API=false on Railway in that case).
    if os.getenv("RUN_MONITOR_IN_API", "true").lower() == "false":
        return

    def run_alert_monitor():
        INTERVAL = 60 * 10  # 10 minutes
        while True:
            try:
                db = SessionLocal()
                triggered = monitoring.check_error_rates(db)
                if triggered:
                    print(f"[ALERT_MONITOR] triggered: {triggered}")
                db.close()
            except Exception as e:
                print(f"[ALERT_MONITOR] error: {e}")
            time.sleep(INTERVAL)

    thread = threading.Thread(target=run_alert_monitor, daemon=True)
    thread.start()


@app.post("/logs")
def create_log(log: LogCreate, db: Session = Depends(get_db)):
    return create_log_logic(log.dict(), db)


@app.get("/alerts/check")
def check_error_rates(db: Session = Depends(get_db)):
    return monitoring.check_error_rates(db)


# ========== DASHBOARD API ENDPOINTS ==========

@app.get("/api/logs/recent")
def get_recent_logs(limit: int = 50, service: str = None, db: Session = Depends(get_db)):
    """Fetch recent logs for dashboard (optionally filtered by service)"""
    return get_recent_logs_logic(limit, db, service=service)


@app.get("/api/alerts/active")
def get_active_alerts(db: Session = Depends(get_db)):
    """Fetch currently active alerts"""
    return get_active_alerts_logic(db)


@app.get("/api/alerts/history")
def get_alert_history(limit: int = 20, db: Session = Depends(get_db)):
    """Fetch alert history"""
    return get_alert_history_logic(limit, db)


@app.get("/api/stats/error-rates")
def get_error_rates_by_service(service: str = None, db: Session = Depends(get_db)):
    """Get current error rates by service (optionally filtered by service)"""
    return get_error_rates_logic(db, service=service)


@app.get("/api/alerts/{alert_id}/rca")
def get_alert_rca(alert_id: int):
    """Return the structured root-cause analysis report for an alert."""
    from app.agents.rca_agent import get_rca

    report = get_rca(alert_id)
    if report is None:
        raise HTTPException(status_code=404, detail="RCA report not available")
    return {"alert_id": alert_id, "rca_report": report}


# Serve dashboard HTML
@app.get("/")
def dashboard():
    """Serve dashboard"""
    return FileResponse("app/static/dashboard.html", media_type="text/html")