import uuid
from sqlalchemy import Column, String, Integer, Text, Enum, TIMESTAMP, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.database import Base
import enum


class LogLevel(enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    

class Log(Base):
    __tablename__ = "logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(Enum(LogLevel, name="log_level"), nullable=False)
    service = Column(String(50), nullable=False)
    user_id = Column(String(255), nullable=True)
    endpoint = Column(String(255), nullable=False)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)
    event_time = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ServiceAlert(Base):
    __tablename__ = "service_alerts"

    service = Column(String(100), primary_key=True)
    last_alert_time = Column(TIMESTAMP(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="false")


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String(100), nullable=False)
    error_rate = Column(Float, nullable=False)
    baseline_rate = Column(Float, nullable=True)
    triggered_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Alert(Base):
    """Unified alert record produced by the LLM monitoring agent.

    This is the integer-keyed source of truth that the agent, RCA pipeline,
    and dashboard operate on. `agent_reasoning` holds the monitoring agent's
    reasoning trace; `rca_report` holds the structured RCA JSON.
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, server_default="MEDIUM")
    status = Column(String(20), nullable=False, server_default="ACTIVE")
    error_rate = Column(Float, nullable=True)
    baseline_rate = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    agent_reasoning = Column(Text, nullable=True)
    rca_report = Column(JSONB, nullable=True)
    triggered_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)
