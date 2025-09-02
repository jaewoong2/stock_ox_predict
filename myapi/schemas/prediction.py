from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import List, Optional
from enum import Enum


class PredictionChoice(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class PredictionStatus(str, Enum):
    PENDING = "PENDING"
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    CANCELLED = "CANCELLED"
    VOID = "VOID"


class PredictionCreate(BaseModel):
    symbol: str = Field(
        ..., pattern=r"^[A-Z]{1,5}$", description="Stock symbol (e.g., AAPL)"
    )
    choice: PredictionChoice = Field(..., description="Prediction choice (UP or DOWN)")

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        return v.upper()


class PredictionUpdate(BaseModel):
    choice: PredictionChoice = Field(..., description="Updated prediction choice")


class PredictionResponse(BaseModel):
    id: int
    user_id: int
    trading_day: date
    symbol: str
    choice: PredictionChoice
    status: PredictionStatus
    submitted_at: datetime
    updated_at: Optional[datetime] = None
    points_earned: Optional[int] = None

    class Config:
        from_attributes = True


class UserPredictionsResponse(BaseModel):
    trading_day: date
    predictions: List[PredictionResponse]
    total_predictions: int
    completed_predictions: int
    pending_predictions: int


class PredictionStats(BaseModel):
    trading_day: date
    total_predictions: int
    up_predictions: int
    down_predictions: int
    correct_predictions: int
    accuracy_rate: float
    points_distributed: int


class PredictionSummary(BaseModel):
    user_id: int
    trading_day: date
    total_submitted: int
    correct_count: int
    incorrect_count: int
    pending_count: int
    accuracy_rate: float
    total_points_earned: int


class UserDailyStatsResponse(BaseModel):
    user_id: int
    trading_day: date
    predictions_made: int
    max_predictions: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
