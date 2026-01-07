from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class PriceBand(BaseModel):
    """가격 밴드 표현 (퍼센트 또는 가격)."""

    low: Optional[Decimal] = None
    high: Optional[Decimal] = None


class CryptoBandPredictionStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    ERROR = "ERROR"


class CryptoBandPredictionCreate(BaseModel):
    """가격 밴드 예측 생성 요청."""

    symbol: str = Field(..., description="예측 심볼 (현재 BTCUSDT만 허용)")
    interval: str = Field(..., description="캔들 간격 (현재 1h만 허용)")
    target_open_time_ms: int = Field(..., description="대상 캔들 시작 시각 (ms)")
    target_close_time_ms: int = Field(..., description="대상 캔들 종료 시각 (ms)")
    row: int = Field(..., ge=0, le=3, description="가격 밴드 행 인덱스 (0~3)")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("interval")
    @classmethod
    def normalize_interval(cls, value: str) -> str:
        return value.lower()


class CryptoBandPredictionSchema(BaseModel):
    """가격 밴드 예측 응답 스키마."""

    id: int
    user_id: int
    trading_day: date
    symbol: str
    interval: str
    future_col: int
    row: int
    target_open_time_ms: int
    target_close_time_ms: int
    p0: Decimal
    band_pct_low: Optional[Decimal] = None
    band_pct_high: Optional[Decimal] = None
    band_price_low: Optional[Decimal] = None
    band_price_high: Optional[Decimal] = None
    status: CryptoBandPredictionStatus
    settlement_price: Optional[Decimal] = None
    settlement_attempts: int = 0
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @computed_field  # type: ignore[misc]
    @property
    def band_pct(self) -> PriceBand:
        return PriceBand(low=self.band_pct_low, high=self.band_pct_high)

    @computed_field  # type: ignore[misc]
    @property
    def band_price(self) -> PriceBand:
        return PriceBand(low=self.band_price_low, high=self.band_price_high)

    @computed_field  # type: ignore[misc]
    @property
    def created_at_ms(self) -> int:
        return int(self.created_at.timestamp() * 1000)


class CryptoBandPredictionListResponse(BaseModel):
    """사용자 예측 목록 응답."""

    predictions: list[CryptoBandPredictionSchema]
    total_count: int
    limit: int
    offset: int
    has_next: bool
