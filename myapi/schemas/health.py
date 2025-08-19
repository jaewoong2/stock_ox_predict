"""Pydantic models for health endpoints."""

from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    """Response model for service health checks."""

    status: str = "healthy"

