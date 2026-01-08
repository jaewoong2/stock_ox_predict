from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from myapi.schemas.prediction import PredictionStatus


class PredictionType(str, Enum):
    DIRECTION = "DIRECTION"
    RANGE = "RANGE"


class CryptoPredictionCreate(BaseModel):
    """크립토 가격 범위 예측 생성 요청."""

    symbol: str = Field(default="BTCUSDT", description="예측 심볼")
    price_low: Decimal = Field(..., description="하한 가격")
    price_high: Decimal = Field(..., description="상한 가격")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class CryptoPredictionSchema(BaseModel):
    """크립토 가격 범위 예측 응답."""

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


class CryptoPredictionListResponse(BaseModel):
    """사용자 크립토 예측 목록 응답."""

    predictions: list[CryptoPredictionSchema]
    total_count: int
    limit: int
    offset: int
    has_next: bool
