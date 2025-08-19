from pydantic import BaseModel, Field, field_validator, model_validator
from decimal import Decimal
from typing import List, Dict, Any, Annotated
from enum import Enum


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


class SettlementSummary(BaseModel):
    trading_day: str
    total_symbols: int
    completed_settlements: int
    pending_settlements: int
    failed_settlements: int
    total_predictions: int
    total_correct: int
    total_incorrect: int
    accuracy_rate: float
    total_points_awarded: int


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
