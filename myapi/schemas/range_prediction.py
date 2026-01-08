"""Range prediction schemas - asset-agnostic price range predictions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from myapi.schemas.prediction import PredictionStatus


class PredictionType(str, Enum):
    """Prediction type enum."""

    DIRECTION = "DIRECTION"
    RANGE = "RANGE"


class RangePredictionCreate(BaseModel):
    """Create RANGE prediction request."""

    symbol: str = Field(..., description="Symbol to predict")
    price_low: Decimal = Field(..., description="Lower bound price")
    price_high: Decimal = Field(..., description="Upper bound price")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize symbol to uppercase."""
        return value.upper()


class RangePredictionUpdate(BaseModel):
    """Update RANGE prediction request."""

    price_low: Optional[Decimal] = Field(None, description="New lower bound price")
    price_high: Optional[Decimal] = Field(None, description="New upper bound price")


class RangePredictionResponse(BaseModel):
    """RANGE prediction response."""

    id: int
    user_id: int
    trading_day: date
    symbol: str
    prediction_type: PredictionType
    price_low: Decimal
    price_high: Decimal
    target_open_time_ms: int
    target_close_time_ms: int
    status: PredictionStatus
    settlement_price: Optional[Decimal] = None
    points_earned: int = 0
    submitted_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class RangePredictionListResponse(BaseModel):
    """List of RANGE predictions response."""

    predictions: list[RangePredictionResponse]
    total_count: int
    limit: int
    offset: int
    has_next: bool


# Backward compatibility aliases
CryptoPredictionCreate = RangePredictionCreate
CryptoPredictionSchema = RangePredictionResponse
CryptoPredictionListResponse = RangePredictionListResponse

