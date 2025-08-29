"""Pydantic models for health endpoints."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    """Response model for service health checks."""

    status: str = "healthy"
    total_errors_today: Optional[int] = None
    system_operational: bool = True
    last_error_logged: Optional[datetime] = None
    error: Optional[str] = None

