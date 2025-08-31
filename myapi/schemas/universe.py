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
    symbols: List[str] = Field(..., min_length=1, max_length=200, description="List of stock symbols")

    @field_validator("symbols")
    @classmethod
    def validate_unique_symbols(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("Duplicate symbols are not allowed")
        return v
    
    @field_validator("symbols")
    @classmethod
    def validate_symbol_format(cls, v: List[str]) -> List[str]:
        import re
        symbol_pattern = re.compile(r"^[A-Z]{1,5}$")
        for symbol in v:
            if not symbol_pattern.match(symbol):
                raise ValueError(f"Invalid symbol format: {symbol}")
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


class UniverseItemWithPrice(BaseModel):
    """가격 정보가 포함된 유니버스 아이템"""

    symbol: str = Field(
        ..., pattern=r"^[A-Z]{1,5}$", description="Stock symbol (e.g., AAPL)"
    )
    seq: int = Field(..., ge=1, le=20, description="Sequence number for ordering")
    company_name: str = Field(..., description="Company name")
    current_price: float = Field(..., description="Current stock price")
    previous_close: float = Field(..., description="Previous close price")
    change_percent: float = Field(
        ..., description="Change percentage from previous close"
    )
    change_direction: str = Field(
        ..., description="Price movement direction (UP/DOWN/FLAT)"
    )
    formatted_change: str = Field(
        ..., description="Formatted change string (e.g., '+2.01%')"
    )

    class Config:
        from_attributes = True


class UniverseWithPricesResponse(BaseModel):
    """가격 정보가 포함된 유니버스 응답"""

    trading_day: str
    symbols: List[UniverseItemWithPrice]
    total_count: int
    last_updated: str = Field(..., description="Last price update timestamp")
