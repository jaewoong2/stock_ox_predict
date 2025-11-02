from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import List, Optional
from decimal import Decimal
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
    # New: price snapshot at prediction time
    prediction_price: Optional[Decimal] = None
    prediction_price_at: Optional[datetime] = None
    prediction_price_source: Optional[str] = None

    # TickerReference 정보 추가
    ticker_name: Optional[str] = None
    ticker_market_category: Optional[str] = None
    ticker_is_etf: Optional[bool] = None
    ticker_exchange: Optional[str] = None

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
    available_predictions: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Prediction Trends Schemas
class MostLongPredictionItem(BaseModel):
    """롱 예측이 가장 많은 종목 정보"""

    ticker: str = Field(..., description="티커 심볼")
    company_name: Optional[str] = Field(None, description="회사명")
    count: int = Field(..., description="롱 예측 횟수")
    win_rate: Optional[float] = Field(None, description="승률 %")
    avg_profit: Optional[float] = Field(None, description="평균 수익률 %")
    last_price: Optional[Decimal] = Field(None, description="최신 가격")
    change_percent: Optional[float] = Field(None, description="변동률 %")


class MostShortPredictionItem(BaseModel):
    """숏 예측이 가장 많은 종목 정보"""

    ticker: str = Field(..., description="티커 심볼")
    company_name: Optional[str] = Field(None, description="회사명")
    count: int = Field(..., description="숏 예측 횟수")
    win_rate: Optional[float] = Field(None, description="승률 %")
    avg_profit: Optional[float] = Field(None, description="평균 수익률 %")
    last_price: Optional[Decimal] = Field(None, description="최신 가격")
    change_percent: Optional[float] = Field(None, description="변동률 %")


class PredictionTrendsResponse(BaseModel):
    """예측 트렌드 응답"""

    most_long_predictions: List[MostLongPredictionItem] = Field(
        default_factory=list, description="롱 예측이 가장 많은 종목 TOP N"
    )
    most_short_predictions: List[MostShortPredictionItem] = Field(
        default_factory=list, description="숏 예측이 가장 많은 종목 TOP N"
    )
    updated_at: datetime = Field(..., description="데이터 업데이트 시간")
