from pydantic import BaseModel, Field, field_validator
from typing import List
from datetime import date


class UniverseItem(BaseModel):
    symbol: str = Field(
        ..., pattern=r"^[A-Z]{1,5}$", description="Stock symbol (e.g., AAPL)"
    )
    seq: int = Field(..., ge=1, le=20, description="Sequence number for ordering")

    class Config:
        from_attributes = True


class UniverseUpdate(BaseModel):
    trading_day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbols: List[UniverseItem] = Field(..., min_length=1, max_length=20)

    @field_validator("symbols")
    @classmethod
    def validate_unique_symbols(cls, v: List[UniverseItem]) -> List[UniverseItem]:
        symbols = [item.symbol for item in v]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate symbols are not allowed")
        return v

    @field_validator("symbols")
    @classmethod
    def validate_unique_sequences(cls, v: List[UniverseItem]) -> List[UniverseItem]:
        sequences = [item.seq for item in v]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Duplicate sequence numbers are not allowed")
        return v


class UniverseResponse(BaseModel):
    trading_day: str
    symbols: List[UniverseItem]
    total_count: int


class UniverseStats(BaseModel):
    trading_day: str
    total_symbols: int
    active_predictions: int
    completion_rate: float
