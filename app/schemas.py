from pydantic import BaseModel
from typing import Optional
from app.models import LogLevel


class LogCreate(BaseModel):
    level: LogLevel
    service: str
    user_id: Optional[str] = None
    endpoint: str
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    message: Optional[str] = None
