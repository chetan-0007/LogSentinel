-- Migration: create unified alerts table
-- Run this SQL against the Postgres database if you are not using Alembic.
-- (The FastAPI app also auto-creates this table via SQLAlchemy on startup.)

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    service VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    error_rate DOUBLE PRECISION,
    baseline_rate DOUBLE PRECISION,
    reason TEXT,
    recommended_action TEXT,
    agent_reasoning TEXT,
    rca_report JSONB,
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_alerts_service ON alerts(service);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);
