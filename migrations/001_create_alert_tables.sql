-- Migration: create alert tables
-- Run this SQL against the Postgres database if you are not using Alembic.

CREATE TABLE IF NOT EXISTS service_alerts (
    service VARCHAR(100) PRIMARY KEY,
    last_alert_time TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    service VARCHAR(100) NOT NULL,
    error_rate DOUBLE PRECISION NOT NULL,
    baseline_rate DOUBLE PRECISION,
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alert_history_service ON alert_history(service);
