from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class UniverseBatchCreate(BaseModel):
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbols: Optional[List[str]] = Field(
        None, 
        max_length=20, 
        description="List of stock symbols. If not provided, uses default tickers"
    )
    use_default: bool = Field(
        True, 
        description="Whether to use default ticker list from docs/tickers.md"
    )


class SessionPhaseTransition(BaseModel):
    trading_day: Optional[str] = Field(
        None, 
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Trading day (YYYY-MM-DD). If not provided, uses current session"
    )
    target_phase: str = Field(
        ..., 
        pattern=r"^(OPEN|CLOSED|SETTLE_READY|SETTLED)$",
        description="Target phase: OPEN, CLOSED, SETTLE_READY, SETTLED"
    )


class BatchSummaryResponse(BaseModel):
    trading_day: str
    session: Optional[dict]
    universe: Optional[dict]


class BatchOperationResponse(BaseModel):
    success: bool
    operation: str
    trading_day: str
    details: dict


class BatchScheduleRequest(BaseModel):
    queue_url: str = Field(..., description="SQS FIFO queue URL")
    workflow_type: str = Field(
        default="daily",
        pattern=r"^(daily|custom)$",
        description="Type of batch workflow to schedule"
    )


class BatchJobStatus(BaseModel):
    operation: str
    description: str
    status: str  # queued, failed, completed
    message_id: Optional[str] = None
    delay_seconds: int = 0
    error: Optional[str] = None


class BatchWorkflowResponse(BaseModel):
    workflow: str
    trading_day: str
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    jobs: List[BatchJobStatus]