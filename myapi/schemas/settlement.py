from pydantic import BaseModel, Field, field_validator, model_validator
from decimal import Decimal
from typing import List, Dict, Any, Annotated, Optional
from enum import Enum
from datetime import datetime


class OutcomeType(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NO_CHANGE = "NO_CHANGE"


class SettlementStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EODDataCreate(BaseModel):
    symbol: str = Field(..., pattern=r"^[A-Z]{1,5}$")
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    open_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    high_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    low_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    close_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    prev_close_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def validate_prices(self) -> "EODDataCreate":
        if self.high_price is not None and self.low_price is not None:
            if self.high_price < self.low_price:
                raise ValueError("High price must be >= low price")
        if (
            self.low_price is not None
            and self.high_price is not None
            and self.close_price is not None
        ):
            if self.close_price < self.low_price or self.close_price > self.high_price:
                raise ValueError("Close price must be between low and high prices")
        return self


class SettlementCreate(BaseModel):
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbol: str = Field(..., pattern=r"^[A-Z]{1,5}$")
    outcome: OutcomeType
    close_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    prev_close_price: Annotated[Decimal, Field(gt=0, multiple_of=0.01)]
    price_change_percent: Annotated[Decimal, Field(multiple_of=0.0001)]

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        return v.upper()


class SettlementResponse(BaseModel):
    id: int
    trading_day: str
    symbol: str
    outcome: OutcomeType
    close_price: Decimal
    prev_close_price: Decimal
    price_change_percent: Decimal
    computed_at: str
    status: SettlementStatus
    predictions_settled: int
    correct_predictions: int
    incorrect_predictions: int
    points_awarded: int

    class Config:
        from_attributes = True


class SymbolSettlementResult(BaseModel):
    symbol: str
    status: str
    reason: Optional[str] = None
    processed_count: int
    correct_count: int
    price_movement: Optional[str] = None
    settlement_price: Optional[float] = None
    change_percent: Optional[float] = None
    accuracy_rate: Optional[float] = 0


class DailySettlementResult(BaseModel):
    trading_day: str
    settlement_completed_at: datetime
    total_predictions_processed: int
    total_correct_predictions: int
    accuracy_rate: float
    symbol_results: List[SymbolSettlementResult]


class SymbolWiseStats(BaseModel):
    symbol: str
    total_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    void_predictions: int
    accuracy_rate: float


class SettlementSummary(BaseModel):
    trading_day: str
    total_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    void_predictions: int
    pending_predictions: int
    overall_accuracy: float
    settlement_status: str
    symbol_statistics: List[SymbolWiseStats]


class ManualSettlementResult(BaseModel):
    symbol: str
    trading_day: str
    manual_settlement: bool
    correct_choice: str
    total_predictions: int
    correct_predictions: int
    accuracy_rate: float


class SettlementStatusResponse(BaseModel):
    trading_day: str
    status: str
    message: Optional[str] = None
    total_symbols: int
    pending_symbols: int
    completed_symbols: int
    failed_symbols: int
    progress_percentage: float
    last_updated: Optional[datetime] = None


class SettlementRetryResultItem(BaseModel):
    symbol: str
    status: str
    message: Optional[str] = None
    processed_count: Optional[int] = None
    correct_count: Optional[int] = None
    reason: Optional[str] = None


class SettlementRetryResult(BaseModel):
    trading_day: str
    retry_completed_at: datetime
    total_symbols_retried: int
    successful_retries: int
    failed_retries: int
    results: List[SettlementRetryResultItem]


class SettlementStats(BaseModel):
    trading_day: str
    symbol: str
    outcome: OutcomeType
    total_predictions: int
    correct_predictions: int
    incorrect_predictions: int
    accuracy_rate: float
    up_predictions: int
    down_predictions: int
    points_distributed: int


class BatchSettlementRequest(BaseModel):
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    eod_data: List[EODDataCreate] = Field(..., min_length=1, max_length=50)

    @classmethod
    def validate_unique_symbols(cls, v: List[EODDataCreate]) -> List[EODDataCreate]:
        symbols = [item.symbol for item in v]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate symbols are not allowed")
        return v


class BatchSettlementResponse(BaseModel):
    trading_day: str
    processed_symbols: List[str]
    successful_settlements: int
    failed_settlements: int
    total_predictions_settled: int
    total_points_awarded: int
    processing_time_seconds: float
    errors: List[Dict[str, Any]] = Field(default_factory=list)
