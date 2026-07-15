"""Standalone monitoring-agent runner.

Runs the same hybrid monitoring cycle as the API's in-process background thread,
but as its own process. Used as a dedicated Railway service. Locally the API
runs the monitor in-process, so this is not needed for docker-compose.

Run: python -m app.run_monitor
"""
import os
import time

from app.database import SessionLocal, engine
from app.models import Base
from app import monitoring

INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", str(60 * 10)))


def main():
    Base.metadata.create_all(bind=engine)
    print(f"[MONITOR] standalone monitor started (interval={INTERVAL}s)")
    while True:
        try:
            db = SessionLocal()
            triggered = monitoring.check_error_rates(db)
            if triggered:
                print(f"[MONITOR] triggered: {triggered}")
            db.close()
        except Exception as e:
            print(f"[MONITOR] error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
