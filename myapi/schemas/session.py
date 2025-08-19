from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from enum import Enum


class SessionPhase(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLING = "SETTLING"


class SessionToday(BaseModel):
    trading_day: str = Field(..., description="Trading day in YYYY-MM-DD format")
    phase: SessionPhase = Field(..., description="Current session phase")
    predict_open_at: str = Field(..., description="When predictions open (KST)")
    predict_cutoff_at: str = Field(..., description="When predictions close (KST)")
    settle_ready_at: Optional[str] = Field(
        None, description="When settlement begins (KST)"
    )
    settled_at: Optional[str] = Field(
        None, description="When settlement completes (KST)"
    )


class Session(SessionToday):
    """세션 정보 (SessionToday와 동일하지만 명시적 정의)"""

    pass


class SessionTransition(BaseModel):
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    new_phase: SessionPhase


class SessionStatus(BaseModel):
    trading_day: date
    phase: SessionPhase
    predict_open_at: datetime
    predict_cutoff_at: datetime
    settle_ready_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    is_prediction_open: bool
    is_settling: bool
    is_closed: bool

    class Config:
        from_attributes = True
